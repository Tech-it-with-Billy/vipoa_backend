"""
CSV Loader utility
Loads recipe data from CSV files into pandas DataFrame
"""

import pandas as pd
from pathlib import Path

class CSVLoader:
    @staticmethod
    def load_recipes(csv_path: str) -> pd.DataFrame:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        df = pd.read_csv(path)
        # Ensure consistent column names
        df.columns = [col.strip().lower() for col in df.columns]
        return df
