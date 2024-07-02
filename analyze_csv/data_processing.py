import pandas as pd
import os

def clean_data(file_path):
    try:
        data = pd.read_csv(file_path, delimiter=';', skiprows=4, on_bad_lines='skip')
    except pd.errors.ParserError as e:
        print("Ошибка парсинга файла:", e)
        return None
    return data

def preprocess_data(data):
    if data is not None:
        data = data.copy()  # Create a copy to avoid SettingWithCopyWarning

        # Удаление двойных кавычек из всех строковых столбцов
        for col in data.select_dtypes(include=['object']).columns:
            data.loc[:, col] = data[col].str.replace('"', '')

        # Определение столбцов для сохранения
        required_columns = ['Заголовок', 'Текст', 'Показы', 'CTR (%)', 'Ср. цена клика (руб.)', 'Отказы (%)', 'Конверсия (%)']
        columns_to_keep = [col for col in required_columns if col in data.columns]

        # Удаление ненужных столбцов
        data = data[columns_to_keep]

        # Заполнение пропущенных значений
        data.fillna(0, inplace=True)

        # Преобразование релевантных столбцов в числовой формат
        data.loc[:, 'CTR (%)'] = pd.to_numeric(data['CTR (%)'].str.replace(',', '.'), errors='coerce').fillna(0).astype(float)
        data.loc[:, 'Ср. цена клика (руб.)'] = pd.to_numeric(data['Ср. цена клика (руб.)'].str.replace(',', '.'), errors='coerce').fillna(0).astype(float)
        data.loc[:, 'Отказы (%)'] = pd.to_numeric(data['Отказы (%)'].str.replace(',', '.'), errors='coerce').fillna(0).astype(float)
        data.loc[:, 'Конверсия (%)'] = pd.to_numeric(data['Конверсия (%)'].str.replace(',', '.'), errors='coerce').fillna(0).astype(float)

        # Группировка по 'Заголовок' и 'Текст' и агрегация метрик
        aggregated_data = data.groupby(['Заголовок', 'Текст']).agg({
            'Показы': 'sum',
            'CTR (%)': 'mean',
            'Ср. цена клика (руб.)': 'mean',
            'Отказы (%)': 'mean',
            'Конверсия (%)': 'mean'
        }).reset_index()

        # Фильтрация строк, где 'Показы' больше 5
        aggregated_data = aggregated_data[aggregated_data['Показы'] > 5]

        return aggregated_data
    else:
        return None

def save_aggregated_data(aggregated_data, output_dir):
    if aggregated_data is not None:
        # Сохранение агрегированных данных в CSV файл
        aggregated_data_csv_path = os.path.join(output_dir, 'aggregated_data.csv')
        aggregated_data.to_csv(aggregated_data_csv_path, index=False, sep=';')
        print(f"Aggregated data saved to {aggregated_data_csv_path}")
    else:
        print("Данные для сохранения не предоставлены.")
