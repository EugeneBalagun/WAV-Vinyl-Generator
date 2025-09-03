
# Usage: python wav_vinyl_generator_gui.py
# Recommendations: r0 (100-2000), b (1-10), amp (10-100) for best results

import os
import sys
import math
import tempfile
import numpy as np
from scipy.io import wavfile
from PIL import Image, ImageDraw
import imageio_ffmpeg
import ffmpeg
import logging
import threading
from PyQt5 import QtWidgets, QtGui, QtCore, QtMultimedia
import traceback
import io

# ---------------- LOGGING SETUP ----------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------------- DEFAULT PARAMETERS ----------------
BACKGROUND_COLOR = 'black'  # фон
CANVAS_SIZE = 2000         # размер холста
INITIAL_COLOR = '#CCCCCC'  # начальный цвет спирали
PROGRESS_COLOR = '#FF0000' # цвет проигранной части
VIDEO_FPS = 10             # частота кадров для видео
VIDEO_QUALITY = 23         # качество видео (CRF для ffmpeg, 0-51, ниже = лучше)

# ---------------- FUNCTIONS ----------------

def convert_to_wav_mono(src_path):
    """
    Конвертит аудиофайл в моно WAV (левый канал), acodec=pcm_s16le.
    Возвращает путь к временному WAV-файлу.
    """
    logger.info(f"Конвертация аудио: {src_path}")
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    out_path = tmp.name
    tmp.close()

    (
        ffmpeg
        .input(src_path)
        .output(out_path,
                format='wav',
                ac=1,
                acodec='pcm_s16le',
                map='0:a:0')
        .global_args('-y')
        .run(cmd=ffmpeg_bin, capture_stdout=True, capture_stderr=True)
    )
    logger.info(f"Конвертация завершена: {out_path}")
    return out_path

def build_spiral(data: np.ndarray, rate: int, r0: float, b: float, amp_scale: float):
    """
    Строит спираль, нормализует сигнал и возвращает массивы координат (x, y).
    """
    logger.info("Построение спирали")
    data = data.astype(np.float32)
    data /= np.max(np.abs(data)) + 1e-9

    n = data.shape[0]
    Rmax = CANVAS_SIZE / 2 * 0.98
    theta_max = (Rmax - r0) / (b + 1e-9)
    thetas = np.linspace(0, theta_max, n)
    radii = r0 + b * thetas + data * amp_scale

    W = CANVAS_SIZE
    C = W // 2
    pts = []
    for theta, r in zip(thetas, radii):
        angle = theta + math.pi / 2
        x = C + r * math.cos(angle)
        y = C + r * math.sin(angle)
        pts.append((x, y))

    logger.info(f"Спираль построена: {len(pts)} точек")
    return pts

def render_vinyl(pts: list, progress: float = 0.0):
    """
    Рисует спираль с изменением цвета в зависимости от прогресса (0.0 - 1.0).
    """
    img = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    total_points = len(pts)
    split_point = int(total_points * progress)

    if split_point > 1:
        draw.line(pts[:split_point], fill=PROGRESS_COLOR, width=1)
    if split_point < total_points:
        draw.line(pts[split_point:], fill=INITIAL_COLOR, width=1)

    return img

def generate_video(audio_path, pts, duration, output_path, progress_callback, cancel_flag):
    """
    Генерирует видео, отправляя кадры в ffmpeg через pipe, с аудио как вторым входом.
    """
    logger.info(f"Начало генерации видео: {output_path}")
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    frame_count = int(duration * VIDEO_FPS)
    frame_size = (CANVAS_SIZE, CANVAS_SIZE)

    try:
        video_stream = ffmpeg.input('pipe:', format='rawvideo', pix_fmt='rgb24', s=f'{frame_size[0]}x{frame_size[1]}', framerate=VIDEO_FPS)
        audio_stream = ffmpeg.input(audio_path)
        process = (
            ffmpeg
            .concat(video_stream, audio_stream, v=1, a=1)
            .output(output_path,
                    vcodec='libx264',
                    crf=VIDEO_QUALITY,
                    pix_fmt='yuv420p',
                    acodec='aac',
                    preset='ultrafast',
                    threads=0)
            .global_args('-y')
            .run_async(pipe_stdin=True, cmd=ffmpeg_bin)
        )

        for i in range(frame_count):
            if cancel_flag.is_set():
                logger.info("Генерация видео прервана пользователем")
                process.terminate()
                process.wait()
                return False
            progress = i / frame_count
            img = render_vinyl(pts, progress)
            img_rgb = img.convert('RGB')
            process.stdin.write(np.array(img_rgb).tobytes())
            if i % max(1, frame_count // 100) == 0:  # обновляем прогресс каждые 1%
                progress_callback(i + 1, frame_count)
                logger.debug(f"Кадр {i+1}/{frame_count} отправлен")
        
        process.stdin.close()
        process.wait()
        logger.info(f"Видео успешно создано: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при генерации видео: {str(e)}")
        raise e

class VinylGenerator(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vinyl Waveform Generator")
        self.setGeometry(100, 100, 600, 500)

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QVBoxLayout(self.central_widget)

        # Кнопка выбора файла
        self.select_button = QtWidgets.QPushButton("Выбрать аудиофайл")
        self.select_button.clicked.connect(self.select_audio)
        self.layout.addWidget(self.select_button)

        # Поле для отображения выбранного файла
        self.file_label = QtWidgets.QLabel("Файл не выбран")
        self.layout.addWidget(self.file_label)

        # Параметры
        self.controls_layout = QtWidgets.QFormLayout()

        self.r0_label = QtWidgets.QLabel("Начальный радиус (r0, рекомендовано 100-2000):")
        self.r0_spin = QtWidgets.QDoubleSpinBox()
        self.r0_spin.setValue(500.0)
        self.r0_spin.setMinimum(-float('inf'))
        self.r0_spin.setMaximum(float('inf'))
        self.controls_layout.addRow(self.r0_label, self.r0_spin)

        self.b_label = QtWidgets.QLabel("Шаг спирали (b, рекомендовано 1-10):")
        self.b_spin = QtWidgets.QDoubleSpinBox()
        self.b_spin.setValue(5.0)
        self.b_spin.setMinimum(-float('inf'))
        self.b_spin.setMaximum(float('inf'))
        self.controls_layout.addRow(self.b_label, self.b_spin)

        self.amp_label = QtWidgets.QLabel("Масштаб амплитуды (amp, рекомендовано 10-100):")
        self.amp_spin = QtWidgets.QDoubleSpinBox()
        self.amp_spin.setValue(40.0)
        self.amp_spin.setMinimum(-float('inf'))
        self.amp_spin.setMaximum(float('inf'))
        self.controls_layout.addRow(self.amp_label, self.amp_spin)

        self.layout.addLayout(self.controls_layout)

        # Кнопки управления
        self.button_layout = QtWidgets.QHBoxLayout()
        self.update_button = QtWidgets.QPushButton("Обновить")
        self.update_button.clicked.connect(self.update_preview)
        self.update_button.setEnabled(False)
        self.button_layout.addWidget(self.update_button)

        self.play_button = QtWidgets.QPushButton("Play/Pause")
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setEnabled(False)
        self.button_layout.addWidget(self.play_button)

        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_play)
        self.stop_button.setEnabled(False)
        self.button_layout.addWidget(self.stop_button)

        self.video_button = QtWidgets.QPushButton("Сгенерировать видео")
        self.video_button.clicked.connect(self.generate_video)
        self.video_button.setEnabled(False)
        self.button_layout.addWidget(self.video_button)

        self.cancel_button = QtWidgets.QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.cancel_video)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        # Прогресс-бар
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        # Область предпросмотра
        self.image_label = QtWidgets.QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.layout.addWidget(self.image_label)

        # Кнопка сохранения
        self.save_button = QtWidgets.QPushButton("Сохранить изображение")
        self.save_button.clicked.connect(self.save_vinyl)
        self.save_button.setEnabled(False)
        self.layout.addWidget(self.save_button)

        self.audio_path = None
        self.audio_data = None
        self.rate = None
        self.image = None
        self.pts = None
        self.player = QtMultimedia.QMediaPlayer()
        self.player.durationChanged.connect(self.update_duration)
        self.duration = 0
        self.cancel_flag = threading.Event()

    def select_audio(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выберите аудиофайл", "",
            "Audio Files (*.mp3 *.aac *.opus *.ogg *.flac *.wav *.m4a *.mp4)"
        )
        if file_path:
            self.audio_path = file_path
            self.file_label.setText(f"Выбран файл: {os.path.basename(file_path)}")
            self.update_button.setEnabled(True)
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.video_button.setEnabled(True)
            self.load_audio()

    def load_audio(self):
        if self.audio_path:
            try:
                wav_path = convert_to_wav_mono(self.audio_path)
                self.rate, data = wavfile.read(wav_path)
                os.unlink(wav_path)
                if data.ndim > 1:
                    data = data[:, 0]
                self.audio_data = data
                self.update_preview()
                self.player.setMedia(QtMultimedia.QMediaContent(QtCore.QUrl.fromLocalFile(self.audio_path)))
            except Exception as e:
                logger.error(f"Ошибка обработки аудио: {str(e)}")
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось обработать аудио: {str(e)}")

    def update_preview(self):
        if self.audio_data is not None:
            r0 = self.r0_spin.value()
            b = self.b_spin.value()
            amp = self.amp_spin.value()

            try:
                self.pts = build_spiral(self.audio_data, self.rate, r0, b, amp)
                self.image = render_vinyl(self.pts)
                self.update_image_label()
                self.save_button.setEnabled(True)
            except Exception as e:
                logger.error(f"Ошибка рендеринга: {str(e)}")
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Ошибка рендеринга: {str(e)}")

    def toggle_play(self):
        if self.player.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_button.setText("Play")
        else:
            self.player.play()
            self.play_button.setText("Pause")

    def stop_play(self):
        self.player.stop()
        self.play_button.setText("Play")

    def update_duration(self, duration):
        self.duration = duration / 1000.0  # в секундах

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        QtWidgets.QApplication.processEvents()

    def generate_video(self):
        if self.audio_path and self.pts and self.duration > 0:
            base_name = os.path.splitext(os.path.basename(self.audio_path))[0]
            out_path = f"{base_name}_vinyl.mp4"
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.video_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.cancel_button.setVisible(True)
            self.cancel_flag.clear()  # Сбрасываем флаг отмены
            try:
                success = generate_video(self.audio_path, self.pts, self.duration, out_path, self.update_progress, self.cancel_flag)
                if success:
                    QtWidgets.QMessageBox.information(self, "Готово", f"Видео сохранено как {out_path}")
                else:
                    QtWidgets.QMessageBox.warning(self, "Прервано", "Генерация видео была отменена")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Ошибка генерации видео: {str(e)}")
            finally:
                self.progress_bar.setVisible(False)
                self.video_button.setEnabled(True)
                self.cancel_button.setEnabled(False)
                self.cancel_button.setVisible(False)

    def cancel_video(self):
        self.cancel_flag.set()  # Устанавливаем флаг отмены
        self.cancel_button.setEnabled(False)

    def update_image_label(self):
        pixmap = QtGui.QPixmap.fromImage(
            QtGui.QImage(self.image.tobytes(), CANVAS_SIZE, CANVAS_SIZE, QtGui.QImage.Format_RGB888)
        ).scaled(400, 400, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)

    def save_vinyl(self):
        if self.audio_path and self.image:
            base_name = os.path.splitext(os.path.basename(self.audio_path))[0]
            out_path = f"{base_name}_vinyl.png"
            self.image.save(out_path, 'PNG')
            QtWidgets.QMessageBox.information(self, "Готово", f"Изображение сохранено как {out_path}")

def main():
    try:
        app = QtWidgets.QApplication(sys.argv)
        window = VinylGenerator()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        logger.error(f"Скрипт завершился с ошибкой: {str(e)}")
        traceback.print_exc()
        input("Нажмите Enter для выхода...")

if __name__ == '__main__':
    main()