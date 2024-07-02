import os
import pandas as pd
import joblib
import json
from catboost import Pool
from data_processing import clean_data, preprocess_data

output_dir = 'output'
os.makedirs(output_dir, exist_ok=True)

current_dir = os.path.dirname(os.path.abspath(__file__))
model_num_path = os.path.join(current_dir, 'output', 'catboost_model_good.pkl')

def main(file_path):
    try:
        data = clean_data(file_path)
        aggregated_data = preprocess_data(data)
        if aggregated_data is not None:
            model_num = joblib.load(model_num_path)
            num_features = ['Показы', 'CTR (%)', 'Ср. цена клика (руб.)', 'Отказы (%)', 'Конверсия (%)']
            X_num = aggregated_data[num_features]
            test_pool = Pool(data=X_num, feature_names=list(X_num.columns))
            y_pred_num = model_num.predict(test_pool)
            aggregated_data['is_selling'] = y_pred_num
            selling_ads_num = aggregated_data[aggregated_data['is_selling'] == 1].to_dict(orient='records')
            
            result_file_path = os.path.join(output_dir, 'analysis_result.json')
            with open(result_file_path, 'w', encoding='utf-8') as f:
                json.dump(selling_ads_num, f, ensure_ascii=False, indent=4)

        else:
            print("Не удалось загрузить или предобработать данные.")
    except Exception as e:
        print(f"Ошибка в анализе данных: {str(e)}")

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
