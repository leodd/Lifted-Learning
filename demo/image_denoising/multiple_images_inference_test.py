import matplotlib.image as img
from utils import show_images, load
from demo.image_denoising.image_data_loader import load_data
import numpy as np
from Graph import *
from NeuralNetPotential import GaussianNeuralNetPotential, ReLU
from Potentials import ImageNodePotential, ImageEdgePotential
from inference.VarInference import VarInference
from inference.EPBPLogVersion import EPBP
from inference.PBP import PBP


USE_MANUAL_POTENTIALS = True

gt_data, noisy_data = load_data('testing/gt', 'testing/noisy')

row = gt_data.shape[1]
col = gt_data.shape[2]

domain = Domain([0, 1], continuous=True)

if USE_MANUAL_POTENTIALS:
    pxo = ImageNodePotential(0, 0.05)
    pxy = ImageEdgePotential(0, 0.035, 0.25)
else:
    pxo = GaussianNeuralNetPotential(
        (2, 64, ReLU()),
        (64, 32, ReLU()),
        (32, 1, None)
    )

    pxy = GaussianNeuralNetPotential(
        (2, 64, ReLU()),
        (64, 32, ReLU()),
        (32, 1, None)
    )

    pxo_params, pxy_params = load(
        'learned_potentials/model_2/3000'
    )

    pxo.set_parameters(pxo_params)
    pxy.set_parameters(pxy_params)

for noisy_image, gt_image in zip(noisy_data, gt_data):
    evidence = [None] * (col * row)
    for i in range(row):
        for j in range(col):
            evidence[i * col + j] = RV(domain, noisy_image[i, j])

    rvs = list()
    for _ in range(row * col):
        rvs.append(RV(domain))

    fs = list()

    # create hidden-obs factors
    for i in range(row):
        for j in range(col):
            fs.append(
                F(
                    pxo,
                    (rvs[i * col + j], evidence[i * col + j])
                )
            )

    # create hidden-hidden factors
    for i in range(row):
        for j in range(col - 1):
            fs.append(
                F(
                    pxy,
                    (rvs[i * col + j], rvs[i * col + j + 1])
                )
            )
    for i in range(row - 1):
        for j in range(col):
            fs.append(
                F(
                    pxy,
                    (rvs[i * col + j], rvs[(i + 1) * col + j])
                )
            )

    g = Graph(rvs + evidence, fs)

    infer = PBP(g, n=20)
    infer.run(10, log_enable=True)

    predict_image = np.empty([row, col])

    for i in range(row):
        for j in range(col):
            predict_image[i, j] = infer.map(rvs[i * col + j])

    show_images([gt_image, noisy_image, predict_image], vmin=0, vmax=1)

    print(np.mean((predict_image - gt_image) ** 2))
