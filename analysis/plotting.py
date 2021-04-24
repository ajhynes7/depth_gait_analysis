"""Functions for plotting points and visualizing results."""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm


def scatter_signal(signal, labels=None, **kwargs):
    """
    Produce a scatter plot of a signal.

    Parameters
    ----------
    signal : (N,) array_like
        Input 1D signal.
    labels : (N,) array_like, optional
        Array of labels.
    kwargs : dict, optional
        Additional keywords passed to `scatter`.

    """
    if labels is None:
        labels = np.ones_like(signal)

    X = np.arange(len(signal))
    points = np.column_stack((X, signal))

    scatter_labels(points, labels, **kwargs)


def scatter_labels(points, labels, **kwargs):
    """
    Scatter points that are coloured by label.

    Parameters
    ----------
    points : (N, 2) ndarray
        Array of N points with dimension 2.
    labels : (N,) ndarray
        Array of point labels.
    kwargs : dict, optional
        Additional keywords passed to `scatter`.

    """
    for label in np.unique(labels):

        points_label = points[labels == label]

        plt.scatter(points_label[:, 0], points_label[:, 1], **kwargs)


def scatter2(points, **kwargs):
    """
    Produce a 2D scatter plot.

    Parameters
    ----------
    points : (N, 2) ndarray
        Array of N points in with dimension 2.
    kwargs : dict, optional
        Additional keywords passed to `scatter`.

    """
    if points.ndim == 1:
        # Convert to 2d array
        points = points.reshape(1, -1)

    plt.scatter(points[:, 0], points[:, 1], **kwargs)


def scatter_series(series, **kwargs):
    """
    Produce a scatter plot from a pandas Series.

    The index is used as the x-values.

    Parameters
    ----------
    series : Series
        Input pandas Series.
    kwargs : dict, optional
        Additional keywords passed to `scatter`.

    """
    plt.scatter(series.index, series, **kwargs)


def connect_points(point_1, point_2, **kwargs):
    """
    Plot a line between two 2D points.

    Parameters
    ----------
    point_1, point_2 : array_like
        Input 2D point.
    kwargs : dict, optional
        Additional keywords passed to `plot`.

    """
    x = [point_1[0], point_2[0]]
    y = [point_1[1], point_2[1]]

    plt.plot(x, y, **kwargs)


def connect_two_sets(points_1, points_2, **kwargs):
    """
    Plot a line between all pairs of points in two sets.

    Parameters
    ----------
    points_1, points_2 : (N, 2) array_like
        Input 2D points.
    kwargs : dict, optional
        Additional keywords passed to `plot`.

    """
    for point_1 in points_1:
        for point_2 in points_2:
            connect_points(point_1, point_2, **kwargs)


def plot_spheres(points, r, ax):
    """
    Plot two-dimensional view of spheres centered on points.

    Parameters
    ----------
    points : array_like
        Points in space.
    r : float
        Radius of spheres.
    ax : Axes
        Axes for plotting.

    """
    for point in points:
        circle = plt.Circle((point[0], point[1]), radius=r, color="black", fill=False)
        ax.add_patch(circle)


def plot_links(points, score_matrix, inside_spheres):
    """
    Plot scored links between points.

    Parameters
    ----------
    points : (N, D) array_like
        Input points.
    score_matrix : (N, N) ndarray
        Score matrix.
    inside_spheres : (N,) ndarray
        Boolean array.
        Element i is True if position i is inside the combined sphere volume.

    """
    for i, point_i in enumerate(points):
        for j, point_j in enumerate(points):

            if inside_spheres[i] and inside_spheres[j]:
                score = score_matrix[i, j]

                if score != 0:
                    # Plot line coloured by score
                    connect_points(
                        point_i, point_j, c=cm.bwr(score), linestyle='-', linewidth=0.75
                    )
