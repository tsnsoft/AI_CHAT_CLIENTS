# -*- coding: utf-8 -*-
import sys
import html        # Для безопасного вывода скобок < и > на экран
import webbrowser  # Для открытия сайта с ключами в браузере
import requests    # Для отправки запросов в интернет (pip install requests)

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTextEdit, QLineEdit, QPushButton,
                             QLabel, QMessageBox, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal

# Ссылка на страницу получения бесплатного ключа Google AI Studio
API_KEY_PAGE_URL = "https://aistudio.google.com/app/api-keys"

# Список доступных моделей для выпадающего списка
AVAILABLE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
]

# Шаблон адреса сервера (вместо {model} подставится выбранная модель)
API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiWorker(QThread):
    """
    Отдельный фоновый поток для отправки запроса в интернет.
    Нужен для того, чтобы главное окно программы не зависало во время ожидания ответа.
    """
    finished_signal = pyqtSignal(str)  # Сигнал при успешном ответе (передаёт текст ответа)
    error_signal = pyqtSignal(str)     # Сигнал при ошибке (передаёт текст ошибки)

    def __init__(self, api_key, model, prompt):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.prompt = prompt

    def run(self):
        """Этот метод запускается автоматически в фоне после команды worker.start()."""
        url = API_URL_TEMPLATE.format(model=self.model)

        # Упаковываем вопрос пользователя в словарь того формата, который ждёт сервер Google
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": self.prompt}
                    ]
                }
            ]
        }

        # 1. Отправляем запрос через интернет
        try:
            response = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=45,
            )
            data = response.json()
        except Exception as e:
            self.error_signal.emit(f"Ошибка сети или формата данных: {e}")
            return

        # 2. Проверяем код ответа сервера (200 означает успех)
        if response.status_code != 200:
            error_info = data.get("error", {})
            message = error_info.get("message", response.text)
            self.error_signal.emit(f"Ошибка {response.status_code}: {message}")
            return

        # 3. Достаём текст ответа простым циклом for
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = ""
            for p in parts:
                # Пропускаем черновые рассуждения модели (если поле "thought" равно True)
                if not p.get("thought"):
                    text = text + p.get("text", "")

            if text.strip() == "":
                self.error_signal.emit("Модель прислала пустой ответ.")
            else:
                self.finished_signal.emit(text)
        except Exception as e:
            self.error_signal.emit(f"Не удалось прочитать ответ сервера: {e}")


class GeminiChatApp(QMainWindow):
    """Главное окно программы: здесь создаются все кнопки, поля ввода и их логика."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini AI Client (PyQt5) — учебная версия")
        self.resize(750, 620)
        self.worker = None  # Сюда будем сохранять объект фонового потока
        self.init_ui()

    def init_ui(self):
        """Создаёт элементы окна и раскладывает их по строкам сверху вниз."""
        # --- 1-й ряд: поле ввода API-ключа и кнопка ---
        key_layout = QHBoxLayout()
        key_label = QLabel("API Key:")
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)  # Скрываем ключ точками
        self.key_input.setPlaceholderText("Вставьте ваш AIzaSy... ключ")

        self.btn_get_key = QPushButton("Получить ключ")
        self.btn_get_key.clicked.connect(self.open_key_page)

        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_input)
        key_layout.addWidget(self.btn_get_key)

        # --- 2-й ряд: выпадающий список моделей ---
        model_layout = QHBoxLayout()
        model_label = QLabel("Модель:")
        self.model_select = QComboBox()
        self.model_select.addItems(AVAILABLE_MODELS)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_select)
        model_layout.addStretch()  # Прижимает список к левому краю

        # --- 3-й ряд: большое поле истории чата ---
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)  # Запрещаем печатать внутри истории вручную
        self.chat_history.setStyleSheet("background: #fdfdfd; font-size: 13px;")

        # --- 4-й ряд: поле ввода вопроса и кнопка «Отправить» ---
        input_layout = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("Введите ваш запрос...")
        self.msg_input.returnPressed.connect(self.send_message)  # Отправка по клавише Enter

        self.btn_send = QPushButton("Отправить")
        self.btn_send.setStyleSheet("background: #0d47a1; color: white; font-weight: bold; padding: 6px 16px;")
        self.btn_send.clicked.connect(self.send_message)         # Отправка по клику мыши

        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(self.btn_send)

        # --- Собираем все 4 ряда в общую вертикальную колонку ---
        layout = QVBoxLayout()
        layout.addLayout(key_layout)
        layout.addLayout(model_layout)
        layout.addWidget(self.chat_history)
        layout.addLayout(input_layout)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def open_key_page(self):
        """Открывает страницу создания ключа в браузере."""
        webbrowser.open(API_KEY_PAGE_URL)

    def send_message(self):
        """Берёт текст из поля ввода и запускает фоновый поток."""
        api_key = self.key_input.text().strip()
        prompt = self.msg_input.text().strip()
        model = self.model_select.currentText()

        # Проверяем, заполнены ли поля
        if api_key == "":
            QMessageBox.warning(self, "Внимание", "Введите API Key от Google AI Studio!")
            return
        if prompt == "":
            return

        # Выводим вопрос пользователя в историю чата
        safe_prompt = html.escape(prompt)
        self.chat_history.append(f"<b>Вы:</b> {safe_prompt}")
        self.msg_input.clear()

        # Временно выключаем кнопку и показываем надпись ожидания внизу окна
        self.btn_send.setEnabled(False)
        self.msg_input.setEnabled(False)
        self.statusBar().showMessage("Gemini генерирует ответ... Пожалуйста, подождите.")

        # Создаём и запускаем фоновый поток
        self.worker = GeminiWorker(api_key, model, prompt)
        self.worker.finished_signal.connect(self.on_success)
        self.worker.error_signal.connect(self.on_error)
        self.worker.finished.connect(self.unlock_ui)
        self.worker.start()

    def on_success(self, text):
        """Срабатывает, когда нейросеть прислала ответ."""
        safe_text = html.escape(text)
        safe_text = safe_text.replace("\n", "<br>")
        self.chat_history.append(f"<b>Gemini:</b> {safe_text}<br>")

    def on_error(self, err_msg):
        """Срабатывает, если произошла ошибка."""
        safe_err = html.escape(err_msg)
        safe_err = safe_err.replace("\n", "<br>")
        self.chat_history.append(f"<b style='color: red;'>Ошибка:</b> {safe_err}<br>")

    def unlock_ui(self):
        """Срабатывает после завершения потока: включает кнопки обратно."""
        self.statusBar().clearMessage()
        self.btn_send.setEnabled(True)
        self.msg_input.setEnabled(True)
        self.msg_input.setFocus()

    def closeEvent(self, event):
        """Не даёт закрыть окно крестиком, пока фоновый поток ещё работает."""
        if self.worker is not None and self.worker.isRunning():
            self.statusBar().showMessage("Дождитесь завершения запроса перед закрытием окна!")
            event.ignore()
            return
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = GeminiChatApp()
    win.show()
    sys.exit(app.exec_())
