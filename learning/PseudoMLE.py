from Graph import *
import numpy as np
import random
from collections import Counter
from optimization_tools import AdamOptimizer


class PseudoMLELearner:
    def __init__(self, g, trainable_potentials, data):
        """
        Args:
            g: The Graph object.
            trainable_potentials: A set of potential functions that need to be trained.
            data: A dictionary that maps each rv to a list of m observed data (list could contain None elements).
        """
        self.g = g
        self.trainable_potentials = trainable_potentials
        self.data = data

        self.M = len(self.data[next(iter(self.data))])  # Number of data frame
        self.latent_rvs = g.rvs - g.condition_rvs
        self.potential_rvs_dict = self.get_potential_rvs_dict(g, trainable_potentials)

    @staticmethod
    def get_potential_rvs_dict(g, potentials):
        """
        Args:
            g: The Graph object.
            potentials: A set of potential functions that need to be trained.

        Returns:
            A dictionary with potential as key and a set of rv as value.
        """
        res = {p: set() for p in potentials}

        for f in g.factors:  # Add all neighboring rvs
            if f.potential in potentials:
                res[f.potential].update(f.nb)

        for p in potentials:  # remove all condition rvs
            res[p] = res[p] - g.condition_rvs

        return res

    def get_unweighted_data(self, rvs, batch, sample_size=10):
        """
        Args:
            rvs: Set of rvs that involve in the Pseudo MLE learning.
            batch: Set of indices of data frame.
            sample_size: The number of sampling points.

        Returns:
            A dictionary with potential as key, and data pairs (x, y) as value.
            Also the data indexing, shift and spacing information.
        """
        potential_count = Counter()  # A counter of potential occurrence
        f_MB = dict()  # A dictionary with factor as key, and local assignment vector as value
        K = len(batch)  # Size of the batch

        for rv in rvs:
            for f in rv.nb:
                potential_count[f.potential] += len(batch)

                if f not in f_MB:
                    f_MB[f] = [
                        [self.data[rv][m] for rv in f.nb]
                        for m in batch
                    ]

        # Initialize data matrix
        data_x = {p: np.array(
            [
                potential_count[p] * ((sample_size + 1) if p in self.trainable_potentials else sample_size),
                p.dimension
            ]
        ) for p in potential_count}

        data_info = dict()  # rv as key, data indexing, shift, spacing as value

        current_idx = Counter()  # Potential as key, index as value
        for rv in rvs:
            # Matrix of starting idx of the potential in the data_x matrix [k, [idx]]
            data_idx_matrix = [[0] * len(rv.nb)] * K

            samples = np.linspace(rv.domain.values[0], rv.domain.values[1], num=sample_size)

            shift = np.random.random(K)
            s = (rv.domain.values[1] - rv.domain.values[0]) / (sample_size - 1)

            for c, f in enumerate(rv.nb):
                rv_idx = rv.nb.index(rv)
                r = 1 if f.potential in self.trainable_potentials else 0

                for k in range(K):
                    next_idx = current_idx[f.potential] + sample_size + r

                    data_x[f.potential][current_idx:next_idx, :] = f_MB[f][k]
                    temp = samples + shift[k] * s
                    temp[0], temp[-1] = samples[0] + shift[k] * s * 0.5, samples[-1] - (1 - shift[k]) * s * 0.5
                    data_x[f.potential][current_idx + r:next_idx, rv_idx] = temp

                    data_idx_matrix[k][c] = current_idx + r

                    current_idx[f.potential] = next_idx

            data_info[rv] = data_idx_matrix, shift, s

        return (data_x, data_info)

    def get_gradient(self, data_x, data_info, sample_size=10):
        """
        Args:
            data_x: The potential input that are computed by get_unweighted_data function.
            data_info: The data indexing, shift and spacing information.
            sample_size: The number of sampling points (need to be consistent with get_unweighted_data function).

        Returns:
            A dictionary with potential as key, and gradient as value.
        """
        data_y = dict()  # A dictionary with a array of output value of the potential functions

        # Forward pass
        for potential, data_matrix in data_x.items():
            data_y[potential] = potential.forward(data_matrix, save_cache=True)

        gradient_y = dict()  # Store of the computed derivative

        # Initialize gradient
        for potential in self.trainable_potentials:
            gradient_y[potential] = np.ones(data_y[potential].shape)

        for rv, (data_idx, shift, s) in data_info.items():
            for start_idx, shift_k in zip(data_idx, shift):
                w = np.zeros(len(rv.nb))

                for f, idx in zip(rv.nb, start_idx):
                    w += data_y[f.potential][idx:idx + sample_size, 0]

                w = np.exp(w) * s
                w[0] *= shift_k
                w[-1] *= (1 - shift_k)
                w /= np.sum(w)

                # Re-weight gradient of sampling points
                for f, idx in zip(rv.nb, start_idx):
                    if f.potential in self.trainable_potentials:
                        gradient_y[f.potential][idx:idx + sample_size, 0] *= -w

        return gradient_y

    def train(self, lr=0.01, max_iter=1000, batch_iter=10, batch_size=1, rvs_selection_size=100, sample_size=10):
        """
        Args:
            lr: Learning rate.
            max_iter: The number of total iterations.
            batch_iter: The number of iteration of each mini batch.
            batch_size: The number of data frame in a mini batch.
            rvs_selection_size: The number of rv that we select in each mini batch.
            sample_size: The number of sampling points.
        """
        adam = AdamOptimizer(lr)
        moments = dict()
        t = 0

        while t < max_iter:
            # For each iteration, compute the gradient w.r.t. each potential function

            # Sample a mini batch of data
            batch = random.sample(
                range(self.M),
                min(batch_size, self.M)
            )

            # And sample a subset of rvs
            rvs = random.sample(
                self.latent_rvs,
                min(rvs_selection_size, len(self.latent_rvs))
            )

            # The computed data set for training the potential function
            # Potential function as key, and data x as value
            data_x, data_info = self.get_unweighted_data(rvs, batch, sample_size)

            i = 0
            while i < batch_iter and t < max_iter:
                gradient_y = self.get_gradient(data_x, data_info, sample_size)

                # Update neural net parameters with back propagation
                for potential, d_y in gradient_y.items():
                    _, d_param = potential.backward(d_y)

                    c = (sample_size + 1) / d_y.shape[0]

                    for layer, (d_W, d_b) in d_param.items():
                        step, moment = adam(d_W * c, moments.get((layer, 'W'), (0, 0)), t + 1)
                        layer.W += step
                        moments[(layer, 'W')] = moment

                        step, moment = adam(d_b * c, moments.get((layer, 'b'), (0, 0)), t + 1)
                        layer.b += step  # Gradient ascent
                        moments[(layer, 'b')] = moment

                i += 1
                t += 1

                print(t)
