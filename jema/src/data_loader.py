import os
import pandas as pd


class DataLoader:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path

    def load_all(self):
        """
        Load all recipe data from the final_african_recipes CSV file.
        This is the single source of truth for all Jema recipe data.
        """
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(
                f"Recipe CSV not found at: {self.csv_path}\n"
                f"Make sure final_african_recipes.csv is in the jema/data/ folder."
            )

        try:
            df = pd.read_csv(self.csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(self.csv_path, encoding="latin-1")

        # Strip whitespace from all column names
        df.columns = [col.strip() for col in df.columns]

        if df.empty:
            empty = pd.DataFrame()
            return {
                "ingredients": empty,
                "ingredient_aliases": empty,
                "recipes": empty,
                "raw_data": empty
            }

        # Ensure meal_name column exists
        if 'meal_name' not in df.columns:
            for alt in ['Meal Name', 'recipe_name', 'name', 'Name']:
                if alt in df.columns:
                    df = df.rename(columns={alt: 'meal_name'})
                    break

        # Ensure core_ingredients column exists
        if 'core_ingredients' not in df.columns:
            for alt in ['ingredients', 'Ingredients', 'Core Ingredients']:
                if alt in df.columns:
                    df = df.rename(columns={alt: 'core_ingredients'})
                    break
            else:
                df['core_ingredients'] = pd.NA

        # Extract unique ingredients from core_ingredients
        all_ingredients = set()
        for ingredients_str in df['core_ingredients'].dropna():
            for ing in str(ingredients_str).split(','):
                cleaned = ing.strip().lower()
                if cleaned:
                    all_ingredients.add(cleaned)

        ingredients_df = pd.DataFrame({
            'ingredient_id': range(1, len(all_ingredients) + 1),
            'names': sorted(all_ingredients)
        })

        aliases_df = pd.DataFrame({
            'alias': sorted(all_ingredients),
            'ingredient_id': range(1, len(all_ingredients) + 1)
        })

        return {
            "ingredients": ingredients_df,
            "ingredient_aliases": aliases_df,
            "recipes": df,
            "raw_data": df
        }

