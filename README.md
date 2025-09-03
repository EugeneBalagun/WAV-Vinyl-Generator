# WAV Vinyl Generator GUI 🎵💿

Visualize audio as a vinyl spiral and generate videos.  
Built with Python using PyQt5, NumPy, SciPy, and FFmpeg.

---

## 📌 Description

The application allows you to:

- Load audio files (MP3, WAV, FLAC, AAC, OGG, M4A, etc.).
- Create a spiral waveform visualization with adjustable parameters:
  - Initial radius `r0` (recommended 100–2000)
  - Spiral step `b` (recommended 1–10)
  - Amplitude scale `amp` (recommended 10–100)
- Play the track directly in the interface.
- Generate a video with the spiral overlaying the audio.
- Save the spiral image as PNG.

---

## 🛠️ Requirements

- Python 3.10+  
- Python libraries:
  ```bash
  pip install numpy scipy pillow pyqt5 imageio-ffmpeg ffmpeg-python
FFmpeg installed and available in PATH (required for video generation).

💻 Installation & Running
Clone the repository:

bash
Copy code
git clone <your-repo-url>
cd wav_vinyl_generator_gui
(Optional) Create a virtual environment:

bash
Copy code
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
Install dependencies:

bash
Copy code
pip install -r requirements.txt
Note: FFmpeg is required for video generation.

Run the application:

bash
Copy code
python wav_vinyl_generator_gui.py
🖱️ Usage
Select an audio file with the "Select Audio File" button.

Adjust spiral parameters (r0, b, amp) as desired.

Click "Update" to preview the spiral.

Play audio using Play/Pause and Stop buttons.

Save the spiral image with "Save Image".

Generate a video with "Generate Video".

Cancel video generation with "Cancel" if needed.

⚠️ Video rendering and large audio files may be resource-intensive.

🛠️ Troubleshooting
FFmpeg not found → Make sure FFmpeg is installed and added to PATH.

Audio conversion error → Only valid audio files are supported.

Application not starting → Check Python version and installed dependencies.

🎨 Recommendations
r0: 100–2000

b: 1–10

amp: 10–100
