import chardet


def yandex_uniter_main():
    # Определение кодировки файла
    def detect_encoding(filename):
        with open(filename, 'rb') as f:
            rawdata = f.read()
            result = chardet.detect(rawdata)
            return result['encoding']

    # Определяем кодировку файлов
    phrases_encoding = detect_encoding('phrases_left.txt')
    shows_encoding = detect_encoding('shows_left.txt')

    # Читаем строки из файлов с определенной кодировкой
    with open('phrases_left.txt', 'r', encoding=phrases_encoding) as phrases_file, \
        open('shows_left.txt', 'r', encoding=shows_encoding) as shows_file:
        
        phrases = phrases_file.readlines()
        shows = shows_file.readlines()

    # Убедимся, что количество строк одинаковое
    assert len(phrases) == len(shows), "Количество строк в файлах не совпадает!"

    # Объединяем запросы и показы в один список кортежей
    combined = list(zip(phrases, shows))

    # Сортируем по убыванию числа показов (предварительно преобразуем показы к int)
    combined_sorted = sorted(combined, key=lambda x: int(x[1]), reverse=True)

    # Удаляем дублирующиеся строки и записываем отсортированные данные в один файл
    seen = set()
    with open('sorted_results.txt', 'w', encoding=phrases_encoding) as sorted_file:
        for phrase, show in combined_sorted:
            if phrase not in seen:
                sorted_file.write(f"{phrase.strip()} {show}")
                seen.add(phrase)

    print("Данные успешно отсортированы, дубли удалены и сохранены в файл 'sorted_results.txt'")


if __name__ == "__main__":
    yandex_uniter_main()