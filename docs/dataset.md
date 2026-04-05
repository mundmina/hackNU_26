1. Publicly Available Engineering Datasets
These are widely used in research for training Health Index and RUL algorithms:
NASA C-MAPSS Dataset: A highly popular public repository containing run-to-failure data from 218 engines, each with measurements from 21 different sensors (e.g., fuel flow, temperature, and pressure)
.
NASA Battery Datasets: Charge-discharge experimental data for lithium-ion batteries, which includes measured signals for temperature, voltage, and current across multiple cycles
.
PRONOSTIA Rolling Bearing Datasets: Includes raw horizontal vibration signals used for model training (Bearings 1-1, 1-2) and model testing (Bearings 1-3, 1-4)
.
MVTec Anomaly Detection Dataset: A standard industrial benchmark for testing unsupervised deep learning models on surface defects
.
2. Specific Railway and Industrial Datasets
Locomotive Braking System Solenoid Valve Dataset: This experimental dataset contains 5,500 training samples and 250 test samples specifically designed for fault classification in locomotive brakes
.
TE33A Wheelset Impact Data: Researchers conducting the "Assessment of the impact of TE33A diesel locomotive wheelsets" have noted that their analyzed datasets are available from the corresponding author upon reasonable request
.
Bane NOR Point Machine Data: This technical study utilized data extracted and aggregated into CSV files from a Postgres database located on-premise at a railway facility, demonstrating that such data is standard for these types of projects
.
3. Synthetic and Simulated Data
The sources emphasize that when high-quality real-world data is scarce, you can generate your own datasets using simulation tools:
Digital Twin Simulation: Creating virtual datasets through 1D or 3D Digital Twin simulations (such as those built in Dymola or Modelica) can solve the challenge of collecting real-world failure data
.
Data Augmentation and Synthesis: For image-based tasks, you can use software-defined virtual sensors or image editing tools to synthesize defects and balance your training set
.
Generative AI: Techniques like GANs and VAEs can be deployed to synthesize fatigue damage datasets or fill in missing information in noisy real-time data streams