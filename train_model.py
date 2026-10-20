"""
Phase 4: train, evaluate and explain a delay-prediction model, then save the
predictions back into the database.

    python train_model.py              # train on the mock data (default)
    python train_model.py --source live

Question the model answers: "this line is running normally at the start of
the hour - will a new delay start during the hour?" (see sql/11_fct_ml_features.sql)

4.2  Time-based train/test split, XGBoost vs two baselines, scored with
     ROC-AUC and PR-AUC (accuracy is useless when ~8% of hours have a delay).
4.3  SHAP explanations -> ml/<source>/*.png
4.4  Predictions -> table ml_predictions in tfl.duckdb + powerbi/data/fct_ml_predictions.parquet

Run python refresh.py first so the features are up to date.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")  # save charts to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from matplotlib.colors import LinearSegmentedColormap
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_DIR = Path(__file__).resolve().parent
DB_FILE = PROJECT_DIR / "tfl.duckdb"
POWERBI_DIR = PROJECT_DIR / "powerbi" / "data"

TARGET = "target_new_delay"
NUMERIC_FEATURES = [
    "hour_of_day", "day_of_week", "is_weekend", "is_bank_holiday", "is_rush_hour",
    "rain_prev_hour_mm", "rain_last_3h_mm", "wind_speed_kmh", "temperature_c",
    "delays_last_24h", "other_lines_disrupted_prev_hour",
]
CATEGORICAL_FEATURES = ["line_id"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Plain-English names for charts and the dashboard
FEATURE_LABELS = {
    "line_id": "Line",
    "hour_of_day": "Hour of day",
    "day_of_week": "Day of week",
    "is_weekend": "Weekend",
    "is_bank_holiday": "Bank holiday",
    "is_rush_hour": "Rush hour",
    "rain_prev_hour_mm": "Rain in previous hour (mm)",
    "rain_last_3h_mm": "Rain in previous 3 hours (mm)",
    "wind_speed_kmh": "Wind speed (km/h)",
    "temperature_c": "Temperature (°C)",
    "delays_last_24h": "Delays on this line in last 24h",
    "other_lines_disrupted_prev_hour": "Other lines disrupted last hour",
}

TEST_SHARE = 0.25        # the most recent 25% of hours are the test set
MIN_EVENTS = 30          # need at least this many delays in train AND test

# Chart colours (validated palette - see powerbi/tfl_theme.json)
BLUE = "#2a78d6"
RED = "#e34948"
INK, MUTED = "#0b0b0b", "#52514e"
FEATURE_VALUE_CMAP = LinearSegmentedColormap.from_list("blues", ["#86b6ef", "#0d366b"])


# ---------------------------------------------------------------- load data
def load_features(source):
    with duckdb.connect(str(DB_FILE), read_only=True) as con:
        df = con.execute(
            "SELECT * FROM fct_ml_features WHERE data_source = ? ORDER BY hour_utc, line_id",
            [source],
        ).fetchdf()
        lines = [r[0] for r in con.execute("SELECT line_id FROM dim_line ORDER BY line_id").fetchall()]
    # fixed list of categories, so the encoding is identical every run
    df["line_id"] = pd.Categorical(df["line_id"], categories=lines)
    return df


def time_split(df):
    """Train on the earlier hours, test on the later ones (never a random split:
    neighbouring hours are similar, so a random split would leak information)."""
    hours = np.sort(df["hour_utc"].unique())
    cutoff = hours[int(len(hours) * (1 - TEST_SHARE))]
    return df[df["hour_utc"] < cutoff].copy(), df[df["hour_utc"] >= cutoff].copy(), cutoff


# ------------------------------------------------------------ 4.2 the models
def make_logistic_regression():
    preprocess = ColumnTransformer([
        ("line", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), NUMERIC_FEATURES),
    ])
    return make_pipeline(preprocess, LogisticRegression(max_iter=1000))


def train_xgboost(train):
    """Shallow trees, a low learning rate and EARLY STOPPING: the last 20% of
    the training period is held back as a validation set, and trees stop being
    added once they no longer improve it. This stops the model memorising noise."""
    hours = np.sort(train["hour_utc"].unique())
    val_cutoff = hours[int(len(hours) * 0.8)]
    fit, val = train[train["hour_utc"] < val_cutoff], train[train["hour_utc"] >= val_cutoff]

    model = xgb.XGBClassifier(
        n_estimators=1000,          # upper limit - early stopping picks the real number
        early_stopping_rounds=50,
        max_depth=3,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        enable_categorical=True,
        tree_method="hist",
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(fit[FEATURES], fit[TARGET], eval_set=[(val[FEATURES], val[TARGET])], verbose=False)
    return model


def score(y_true, y_prob):
    return {
        "roc_auc": round(roc_auc_score(y_true, y_prob), 3),       # ranking: 0.5 = random, 1 = perfect
        "pr_auc": round(average_precision_score(y_true, y_prob), 3),  # precision/recall on the rare class
        "brier": round(brier_score_loss(y_true, y_prob), 4),       # probability accuracy (lower = better)
    }


# ---------------------------------------------------------- 4.3 explanations
def shap_values(model, X):
    """Exact TreeSHAP values from XGBoost itself (supports the categorical line
    column natively). Last column of the output is the base value."""
    contribs = model.get_booster().predict(
        xgb.DMatrix(X, enable_categorical=True), pred_contribs=True
    )
    return contribs[:, :-1], contribs[:, -1]


def restyle_shap_colours(fig):
    """SHAP draws in its own pink/blue. Swap them for the validated palette:
    marks get RED (raises risk) / BLUE (lowers risk), and value labels drawn in
    those colours get neutral text ink (text never wears the series colour)."""
    def close(colour, target):
        return np.allclose(matplotlib.colors.to_rgb(colour), target, atol=0.08)

    pink, blue = shap.plots.colors.red_rgb, shap.plots.colors.blue_rgb
    for ax in fig.axes:
        for patch in ax.patches:
            if close(patch.get_facecolor(), pink):
                patch.set_facecolor(RED); patch.set_edgecolor(RED)
            elif close(patch.get_facecolor(), blue):
                patch.set_facecolor(BLUE); patch.set_edgecolor(BLUE)
        for text in ax.texts:
            if close(text.get_color(), pink) or close(text.get_color(), blue):
                text.set_color(MUTED)


def save_shap_charts(values, base_values, X, out_dir, source):
    labels = [FEATURE_LABELS[f] for f in X.columns]
    # numeric version of the data for colouring points (line -> category code)
    X_numeric = X.copy()
    X_numeric["line_id"] = X_numeric["line_id"].cat.codes
    explanation = shap.Explanation(
        values=values, base_values=base_values, data=X_numeric.to_numpy(dtype=float), feature_names=labels
    )
    simulated = " (SIMULATED DATA)" if source == "mock" else ""

    # 1. Which features matter most overall (mean absolute SHAP value)
    plt.figure()
    shap.plots.bar(explanation, max_display=12, show=False)
    restyle_shap_colours(plt.gcf())
    for bar in plt.gca().patches:
        bar.set_color(BLUE)
    plt.title(f"What drives the predicted delay risk{simulated}", color=INK, loc="left")
    plt.xlabel("Average impact on predicted risk (mean |SHAP value|)", color=MUTED)
    plt.savefig(out_dir / "shap_importance.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2. How each feature's VALUE pushes risk up or down (one dot per line-hour)
    plt.figure()
    shap.plots.beeswarm(explanation, max_display=12, color=FEATURE_VALUE_CMAP, show=False)
    plt.title(f"How each feature moves the risk{simulated}", color=INK, loc="left")
    plt.xlabel("SHAP value: right = higher delay risk, left = lower", color=MUTED)
    plt.savefig(out_dir / "shap_beeswarm.png", dpi=150, bbox_inches="tight")
    plt.close()


def save_single_prediction_chart(values, base_value, row, probability, average_rate, out_dir, source, title):
    """Waterfall chart for one prediction: why did the model say this?"""
    display = row.copy().astype(object)
    display["line_id"] = str(row["line_id"])
    explanation = shap.Explanation(
        values=values, base_values=base_value,
        data=display.to_numpy(), feature_names=[FEATURE_LABELS[f] for f in row.index],
    )
    plt.figure()
    shap.plots.waterfall(explanation, max_display=10, show=False)
    restyle_shap_colours(plt.gcf())
    simulated = " (SIMULATED DATA)" if source == "mock" else ""
    plt.title(title + simulated, color=INK, loc="left", fontsize=10, pad=28)
    plt.xlabel(f"Model score (log-odds). Red pushes risk up, blue down. "
               f"Average hour: {average_rate:.0%} risk -> this hour: {probability:.0%}", color=MUTED, fontsize=9)
    plt.savefig(out_dir / "shap_example_prediction.png", dpi=150, bbox_inches="tight")
    plt.close()


def top_reason(shap_row, feature_names):
    """The single feature that pushed this prediction's risk up the most."""
    i = int(np.argmax(shap_row))
    return FEATURE_LABELS[feature_names[i]] if shap_row[i] > 0 else "No strong risk factor"


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["mock", "live"], default="mock")
    source = parser.parse_args().source

    out_dir = PROJECT_DIR / "ml" / source
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_features(source)
    train, test, cutoff = time_split(df)
    print(f"Data: {source} | {len(df):,} line-hours | {int(df[TARGET].sum())} delays "
          f"({df[TARGET].mean():.1%} of hours)")
    print(f"Train: {len(train):,} rows before {pd.Timestamp(cutoff):%Y-%m-%d %H:%M} UTC, "
          f"{int(train[TARGET].sum())} delays")
    print(f"Test:  {len(test):,} rows from then on, {int(test[TARGET].sum())} delays")

    if train[TARGET].sum() < MIN_EVENTS or test[TARGET].sum() < MIN_EVENTS:
        print(f"\nNot enough delays to train and test reliably (need {MIN_EVENTS}+ in each). "
              "Collect more data and try again.")
        return

    # ---- 4.2 train and compare against baselines
    base_rate = train[TARGET].mean()
    results = {"Baseline (always the average rate)": score(test[TARGET], np.full(len(test), base_rate))}

    logreg = make_logistic_regression().fit(train[FEATURES], train[TARGET])
    results["Logistic regression"] = score(test[TARGET], logreg.predict_proba(test[FEATURES])[:, 1])

    model = train_xgboost(train)
    test_prob = model.predict_proba(test[FEATURES])[:, 1]
    results["XGBoost"] = score(test[TARGET], test_prob)
    print(f"\nXGBoost early stopping kept {model.best_iteration + 1} trees")

    print("\nTest-set results (higher ROC-AUC / PR-AUC = better, lower Brier = better):")
    print(pd.DataFrame(results).T.to_string())
    print(f"(PR-AUC of a useless model = the delay rate, {test[TARGET].mean():.3f})")

    # ---- 4.3 explain with SHAP (on the test set: how the model behaves on new data)
    values, base_values = shap_values(model, test[FEATURES])
    save_shap_charts(values, base_values, test[FEATURES], out_dir, source)

    i = int(np.argmax(test_prob))  # explain the highest-risk test prediction
    row = test.iloc[i]
    title = (f"Why the model rated {row['line_id']} at "
             f"{pd.Timestamp(row['hour_london']):%a %d %b %H:00} high-risk ({test_prob[i]:.0%})")
    save_single_prediction_chart(values[i], base_values[i], test[FEATURES].iloc[i],
                                 test_prob[i], base_rate, out_dir, source, title)
    print(f"\nSHAP charts saved to {out_dir.relative_to(PROJECT_DIR)}/")

    # ---- 4.4 predictions for every line-hour -> database + Power BI
    all_prob = model.predict_proba(df[FEATURES])[:, 1]
    all_values, _ = shap_values(model, df[FEATURES])
    trained_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    predictions = pd.DataFrame({
        "data_source": source,
        "line_id": df["line_id"].astype(str),
        "hour_utc": df["hour_utc"],
        "hour_london": df["hour_london"],
        "date_london": pd.to_datetime(df["hour_london"]).dt.date,
        "hour_of_day": df["hour_of_day"],
        # predictions on training rows look better than reality - label them
        "dataset_split": np.where(df["hour_utc"] < cutoff, "train", "test"),
        "predicted_risk": all_prob.round(4),
        "risk_vs_average": (all_prob / base_rate).round(2),
        "top_risk_factor": [top_reason(v, FEATURES) for v in all_values],
        "actual_new_delay": df[TARGET],
        "model": "XGBoost",
        "trained_at_utc": trained_at,
    })
    predictions["risk_band"] = pd.cut(
        predictions["risk_vs_average"], bins=[-np.inf, 1.25, 1.75, np.inf],
        labels=["Normal", "Elevated", "High"],
    ).astype(str)

    with duckdb.connect(str(DB_FILE)) as con:
        con.register("new_predictions", predictions)
        con.execute("CREATE TABLE IF NOT EXISTS ml_predictions AS SELECT * FROM new_predictions WHERE FALSE")
        # replace this source's predictions, keep the other source's
        con.execute("DELETE FROM ml_predictions WHERE data_source = ?", [source])
        con.execute("INSERT INTO ml_predictions BY NAME SELECT * FROM new_predictions")
        con.execute(f"COPY ml_predictions TO '{(POWERBI_DIR / 'fct_ml_predictions.parquet').as_posix()}' (FORMAT parquet)")
        saved = con.execute("SELECT COUNT(*) FROM ml_predictions WHERE data_source = ?", [source]).fetchone()[0]

    metrics = {"source": source, "trained_at_utc": trained_at, "cutoff_utc": str(pd.Timestamp(cutoff)),
               "train_rows": len(train), "test_rows": len(test), "base_rate": round(base_rate, 4),
               "results": results}
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    model.save_model(out_dir / "model.json")
    print(f"Saved {saved:,} predictions to tfl.duckdb (ml_predictions) "
          f"and powerbi/data/fct_ml_predictions.parquet")


if __name__ == "__main__":
    main()
