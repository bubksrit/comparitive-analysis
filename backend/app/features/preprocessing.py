"""Train-fitted preprocessing builders for already audited feature frames."""

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def build_preprocessor(training_features: pd.DataFrame) -> ColumnTransformer:
    """Create, but do not fit, a transformer inferred only from training columns/dtypes.

    Numeric values use train-fitted median imputation. Categorical values use train-fitted
    most-frequent imputation and one-hot encoding. No scaling is applied because the planned
    Random Forest evaluator does not need it. Call ``fit``/``fit_transform`` on training data
    only, then use ``transform`` on validation/test data.
    """
    numeric_columns = list(training_features.select_dtypes(include="number").columns)
    categorical_columns = [column for column in training_features.columns if column not in numeric_columns]
    transformers = []
    if numeric_columns:
        transformers.append(("numeric", SimpleImputer(strategy="median"), numeric_columns))
    if categorical_columns:
        categorical_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("encoder", OneHotEncoder(handle_unknown="ignore")),
            ]
        )
        transformers.append(("categorical", categorical_pipeline, categorical_columns))
    if not transformers:
        raise ValueError("Cannot build a preprocessing pipeline with zero training features")
    return ColumnTransformer(transformers=transformers, remainder="drop")
