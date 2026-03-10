import pandas as pd


class DataLoader:
    def __init__(self, excel_path: str):
        self.excel_path = excel_path

    def load_all(self):
        # Load every sheet from the Excel file instead of a hard-coded list
        try:
            workbook = pd.ExcelFile(self.excel_path)
            sheet_names = workbook.sheet_names
        except Exception as e:
            raise ValueError(f"Could not open Excel file '{self.excel_path}': {e}")

        all_recipes = []
        for sheet in sheet_names:
            try:
                df = workbook.parse(sheet_name=sheet)
                if df.empty:
                    continue
                all_recipes.append(df)
            except Exception as e:
                print(f"Warning: Could not load sheet '{sheet}': {e}")
        
        # Combine all recipes
        if not all_recipes:
            # Return empty frames if nothing was loaded
            empty = pd.DataFrame()
            return {
                "ingredients": empty,
                "ingredient_aliases": empty,
                "recipes": empty,
                "raw_data": empty
            }

        recipes_df = pd.concat(all_recipes, ignore_index=True)

        # Ensure the expected column exists
        if 'core_ingredients' not in recipes_df.columns:
            recipes_df['core_ingredients'] = pd.NA
        
        # Extract unique ingredients from core_ingredients column
        all_ingredients = set()
        for ingredients_str in recipes_df['core_ingredients'].dropna():
            # Split by common separators
            ingredients = str(ingredients_str).split(',')
            for ing in ingredients:
                cleaned = ing.strip().lower()
                if cleaned:
                    all_ingredients.add(cleaned)
        
        # Create ingredients dataframe
        ingredients_df = pd.DataFrame({
            'ingredient_id': range(1, len(all_ingredients) + 1),
            'names': sorted(all_ingredients)
        })
        
        # Create simple aliases (each ingredient name is its own alias)
        aliases_df = pd.DataFrame({
            'alias': sorted(all_ingredients),
            'ingredient_id': range(1, len(all_ingredients) + 1)
        })
        
        return {
            "ingredients": ingredients_df,
            "ingredient_aliases": aliases_df,
            "recipes": recipes_df,
            "raw_data": recipes_df  # Keep original for reference
        }

