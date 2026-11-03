import sys
import os
import html        # Для безопасного вывода текста на экран (чтобы скобки < > не ломали разметку)
import webbrowser  # Чтобы открывать ссылки в браузере
import requests    # Для отправки запросов в интернет (к серверу Gemini)

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextEdit, QLineEdit, QPushButton,
                             QLabel, QMessageBox, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal  # Для работы в фоновом режиме (чтобы окно не зависало)
from PyQt5.QtGui import QTextCursor           # Для управления курсором в текстовом поле

# Ссылка на сайт, где каждый студент должен получить свой бесплатный ключ
API_KEY_PAGE_URL = "https://aistudio.google.com/app/api-keys"

# Список доступных версий нейросети для выпадающего списка
AVAILABLE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
]

# Адрес сервера Google, куда программа отправляет вопросы (вместо {model} подставится выбранная модель)
API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiWorker(QThread):
    """
    Отдельный фоновый поток для общения с нейросетью.
    Если делать запрос прямо в главном окне, программа зависнет на несколько секунд, пока ждет ответ.
    """
    # Сигналы нужны, чтобы передать результат из фонового потока обратно в главное окно
    finished_signal = pyqtSignal(str)  # Сигнал при успехе (передает текст ответа)
    error_signal = pyqtSignal(str)     # Сигнал при ошибке (передает текст ошибки)

    def __init__(self, api_key, model, prompt):
        super().__init__()
        self.api_key = api_key  # Ключ доступа
        self.model = model      # Выбранная модель ИИ
        self.prompt = prompt    # Текст вопроса от пользователя

    def run(self):
        """Этот метод запускается автоматически при старте потока и отправляет запрос."""
        url = API_URL_TEMPLATE.format(model=self.model)
        headers = {"Content-Type": "application/json"}

        # Упаковываем вопрос пользователя в формат словаря, который понимает сервер Google
        payload = {
            "contents": [
                {"parts": [{"text": self.prompt}]}
            ]
        }

        # 1. Пробуем отправить запрос через интернет (ждем максимум 45 секунд)
        try:
            response = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                headers=headers,
                timeout=45,
            )
        except requests.exceptions.Timeout:
            self.error_signal.emit("Превышено время ожидания (45 сек). Проверьте интернет или VPN!")
            return
        except requests.exceptions.ConnectionError:
            self.error_signal.emit("Нет связи с сервером Google. Проверьте интернет или VPN!")
            return
        except requests.exceptions.RequestException as e:
            self.error_signal.emit(f"Ошибка сети: {e}")
            return

        # 2. Пробуем перевести ответ сервера из формата JSON в обычный словарь Python
        try:
            data = response.json()
        except ValueError:
            print("--- ОШИБКА: Сервер вернул не JSON ---")
            print("Код ответа:", response.status_code)
            print(response.text[:1000])
            self.error_signal.emit(f"Непонятный ответ от сервера (код {response.status_code}). Подробности в консоли.")
            return

        # 3. Достаем сам текст ответа из полученного словаря
        try:
            # Код 200 означает, что сервер успешно обработал наш запрос
            if response.status_code == 200:
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        # Собираем кусочки текста в один ответ (пропуская черновые мысли модели "thought")
                        text = "".join(
                            p["text"]
                            for p in parts
                            if isinstance(p, dict)
                            and isinstance(p.get("text"), str)
                            and not p.get("thought", False)
                        )

                        if not text.strip():
                            self.error_signal.emit("Нейросеть прислала пустой текст.")
                            return

                        # Все прошло успешно — отправляем готовый текст в главное окно
                        self.finished_signal.emit(text)
                        return

                self.error_signal.emit("Пустой ответ от модели (возможно, запрос заблокирован фильтром безопасности).")
            else:
                # Если код ответа не 200 (например, неверный ключ или превышен лимит запросов)
                err_info = data.get("error", {})
                code = err_info.get("code", response.status_code)
                msg = err_info.get("message", response.text)
                self.error_signal.emit(f"Ошибка {code}: {msg}")
        except (TypeError, AttributeError, KeyError, IndexError) as e:
            self.error_signal.emit(f"Не удалось прочитать структуру ответа: {e}")


class GeminiChatApp(QMainWindow):
    """Главное окно программы: здесь создаются все кнопки, поля ввода и логика их работы."""

    PLACEHOLDER_TEXT = "Gemini генерирует ответ..."

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini AI Client (PyQt5) — учебная версия")
        self.resize(750, 620)               # Задаем ширину и высоту окна
        self.worker = None                  # Сюда будем сохранять запущенный фоновый поток
        self._placeholder_start = None      # Позиция временной надписи «генерирует ответ...»

        self.init_ui()                      # Вызываем метод отрисовки интерфейса

    def init_ui(self):
        """Создает все элементы интерфейса и размещает их в окне."""

        # --- 1. Верхняя строка: ввод API-ключа ---
        key_layout = QHBoxLayout()
        key_label = QLabel("API Key:")
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)  # Скрываем вводимые символы звездочками
        self.key_input.setPlaceholderText("Вставьте ваш AIzaSy... ключ")

        # Если ключ уже сохранен в системе (переменная среды), подставляем его автоматически
        saved_key = os.getenv("GEMINI_API_KEY", "")
        if saved_key:
            self.key_input.setText(saved_key)

        self.btn_get_key = QPushButton("Получить ключ")
        self.btn_get_key.setToolTip("Откроет сайт Google для создания бесплатного ключа")
        self.btn_get_key.clicked.connect(self.open_api_key_page)

        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_input)
        key_layout.addWidget(self.btn_get_key)

        # --- 2. Вторая строка: выпадающий список моделей ---
        model_layout = QHBoxLayout()
        model_label = QLabel("Модель:")
        self.model_select = QComboBox()
        self.model_select.addItems(AVAILABLE_MODELS)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_select)
        model_layout.addStretch()  # Прижимает список моделей к левому краю

        # --- 3. Центральная часть: поле истории чата ---
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)  # Запрещаем печатать прямо в истории сообщений
        self.chat_history.setStyleSheet("background: #fdfdfd; font-size: 13px; line-height: 1.4;")

        # --- 4. Нижняя строка: поле ввода вопроса и кнопка «Отправить» ---
        input_layout = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("Введите ваш запрос...")
        self.msg_input.returnPressed.connect(self.send_message)  # Отправка по клавише Enter

        self.btn_send = QPushButton("Отправить")
        self.btn_send.setStyleSheet("background: #0d47a1; color: white; font-weight: bold; padding: 6px 16px;")
        self.btn_send.clicked.connect(self.send_message)         # Отправка по клику мыши

        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(self.btn_send)

        # --- Собираем все строки сверху вниз в один общий блок ---
        layout = QVBoxLayout()
        layout.addLayout(key_layout)
        layout.addLayout(model_layout)
        layout.addWidget(self.chat_history)
        layout.addLayout(input_layout)

        # Размещаем собранный блок в главном окне
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def open_api_key_page(self):
        """Открывает в браузере сайт для получения API-ключа."""
        webbrowser.open(API_KEY_PAGE_URL)

    def send_message(self):
        """Берет текст из поля ввода и запускает отправку запроса."""
        # Если предыдущий запрос еще работает, новый не запускаем
        if self.worker is not None:
            return

        api_key = self.key_input.text().strip()  # .strip() убирает лишние пробелы по краям
        prompt = self.msg_input.text().strip()
        model = self.model_select.currentText()

        # Проверяем, ввел ли пользователь ключ и текст вопроса
        if not api_key:
            QMessageBox.warning(self, "Внимание", "Введите API Key от Google AI Studio (начинается на AIzaSy...)")
            return
        if not prompt:
            return

        # Выводим вопрос пользователя в историю чата
        self.chat_history.append(f"<b>Вы:</b> {html.escape(prompt)}")

        # Запоминаем место в конце текста и пишем временную фразу «Gemini генерирует ответ...»
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._placeholder_start = cursor.position()
        self.chat_history.append(f"<i>{self.PLACEHOLDER_TEXT}</i>")

        self.msg_input.clear()  # Очищаем поле ввода

        # Временно выключаем кнопку и поле ввода, пока ждем ответ
        self.btn_send.setEnabled(False)
        self.msg_input.setEnabled(False)

        # Создаем и запускаем фоновый поток
        self.worker = GeminiWorker(api_key, model, prompt)
        self.worker.finished_signal.connect(self.on_success)    # Если всё хорошо -> вызовет on_success
        self.worker.error_signal.connect(self.on_error)          # Если ошибка -> вызовет on_error
        self.worker.finished.connect(self.on_worker_finished)    # Когда поток завершится -> включит кнопки обратно
        self.worker.start()

    def _remove_placeholder(self):
        """Удаляет временную надпись 'Gemini генерирует ответ...' перед выводом результата."""
        if self._placeholder_start is None:
            return

        # Выделяем текст от начала временной надписи до самого конца и удаляем его
        cursor = self.chat_history.textCursor()
        cursor.setPosition(self._placeholder_start)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        self._placeholder_start = None

    def on_success(self, text):
        """Срабатывает, когда нейросеть прислала ответ."""
        self._remove_placeholder()
        # Заменяем переносы строк (\n) на HTML-тег <br>, чтобы абзацы отображались правильно
        safe_text = html.escape(text).replace("\n", "<br>")
        self.chat_history.append(f"<b>Gemini:</b> {safe_text}<br>")

    def on_error(self, err_msg):
        """Срабатывает, если произошла ошибка."""
        self._remove_placeholder()
        safe_err = html.escape(err_msg).replace("\n", "<br>")
        self.chat_history.append(f"<b style='color: red;'>Ошибка:</b> {safe_err}<br>")

    def on_worker_finished(self):
        """Срабатывает в самом конце работы потока (и при успехе, и при ошибке)."""
        worker = self.worker
        self.worker = None

        if worker is not None:
            worker.deleteLater()  # Очищаем память от завершенного потока

        self.statusBar().clearMessage()
        self.unlock_ui()          # Включаем кнопки обратно

    def unlock_ui(self):
        """Включает поле ввода и кнопку 'Отправить' для следующего вопроса."""
        self.btn_send.setEnabled(True)
        self.msg_input.setEnabled(True)
        self.msg_input.setFocus()  # Ставим мигающий курсор обратно в поле ввода

    def closeEvent(self, event):
        """Проверяет, можно ли закрыть окно программы при нажатии на крестик."""
        # Если запрос еще идет, просим подождать и отменяем закрытие, чтобы программа не выдала ошибку
        if self.worker is not None and self.worker.isRunning():
            self.statusBar().showMessage(
                "Запрос ещё выполняется. Дождитесь завершения и закройте окно повторно."
            )
            event.ignore()
            return
        event.accept()


# Точка входа: отсюда начинается запуск программы
if __name__ == "__main__":
    app = QApplication(sys.argv)  # Создаем приложение
    win = GeminiChatApp()         # Создаем главное окно
    win.show()                    # Показываем окно на экране
    sys.exit(app.exec_())         # Запускаем основной цикл работы окна