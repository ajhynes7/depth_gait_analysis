"""
Module for estimating the pose of a walking person.

The pose is estimated by selecting body parts from a set of hypotheses.

"""
import itertools

import numpy as np
from scipy.spatial.distance import cdist

import modules.graphs as gr
import modules.linear_algebra as lin
import modules.general as gen


def only_consecutive_labels(label_adj_list):
    """
    Return a label adjacency list with only consecutive labels.

    For example, if the original adjacency list includes 2->3, 3->4, and 2->4,
    the returned adjacency list will only have 2->3 and 3->4.

    Parameters
    ----------
    label_adj_list : dict
        Adjacency list for the labels.
        label_adj_list[A][B] is the expected distance between
        a point with label A and a point with label B.

    Returns
    -------
    consecutive_adj_list : dict
        Adjacency list for consecutive labels only.
        Every key in original label_adj_list is included.

    Examples
    --------
    >>> label_adj_list = {0: {1: 6}, 1: {2: 1, 3: 3}, 3: {4: 20}, 4: {5: 20}}

    >>> only_consecutive_labels(label_adj_list)
    {0: {1: 6}, 1: {2: 1}, 3: {4: 20}, 4: {5: 20}}

    """
    consecutive_adj_list = {k: {} for k in label_adj_list}

    for key_1 in label_adj_list:
        for key_2 in label_adj_list[key_1]:

            if key_2 - key_1 == 1:

                consecutive_adj_list[key_1] = {
                    key_2: label_adj_list[key_1][key_2]}

    return consecutive_adj_list


def estimate_lengths(pop_series, label_series, cost_func, n_frames, eps=0.01):
    """
    Estimate the lengths between consecutive body parts (e.g., calf to foot).

    Starting with an initial estimate of zeros, the lengths are updated by
    iterating over a number of frames and taking the median of the results.

    Parameters
    ----------
    pop_series : Series
        Index of the series is image frame numbers.
        Value at each frame is the population of body part hypotheses.
    label_series : Series
        Index of the series is image frame numbers.
        Value at each frame is the labels of the body part hypotheses.
    cost_func : function
        Cost function for creating the weighted graph.
    n_frames : int
        Number of frames used to estimate the lengths.
    eps : float, optional
        The convergence criterion epsilon (the default is 0.01).
        When all lengths have changed by less
        than epsilon from the previous iteration,
        the iterative process ends.

    Returns
    -------
    lengths : ndarray
        1-D array of estimated lengths between adjacent parts.

    """
    n_lengths = label_series.iloc[0].max()

    # List of image frames with data
    frames = pop_series.index.values

    # Initial estimate of lengths
    lengths = np.zeros(n_lengths)

    while True:

        prev_lengths = lengths

        length_dict = {i: {i + 1: length} for i, length in enumerate(lengths)}
        length_dict[n_lengths] = {}

        length_array = np.full((n_frames, n_lengths), np.nan)

        for i, f in enumerate(frames[:n_frames]):

            population = pop_series.loc[f]
            labels = label_series.loc[f]

            prev, dist = pop_shortest_paths(population, labels,
                                            length_dict, cost_func)

            label_dict = gen.iterable_to_dict(labels)
            min_path = gr.min_shortest_path(prev, dist, label_dict, n_lengths)

            min_pop = population[min_path]

            length_array[i, :] = list(lin.consecutive_dist(min_pop))

        # Update lengths
        lengths = np.median(length_array, axis=0)

        if np.all(abs(lengths - prev_lengths)) < eps:
            break

    return lengths


def get_population(frame_series, part_labels):
    """
    Return the population of part hypotheses from one image frame.

    Parameters
    ----------
    frame_series : Series
        Index of the series is body parts.
        Values of the series are part hypotheses.
    part_labels : array_like
        Label for each body part in the series.
        e.g. L_FOOT and R_FOOT both have the label 5.

    Returns
    -------
    population : ndarray
        (n, 3) array of n positions.
    labels : ndarray
        (n,) array of labels for n positions.
        The labels correspond to body part types (e.g., foot).
        They are sorted in ascending order.

    Examples
    --------
    >>> import pandas as pd
    >>> head_points = np.array([-45, 66, 238]).reshape(-1, 3)
    >>> foot_points = np.array([[-26., -57, 249], [-74, -58, 260]])

    >>> frame_series = pd.Series({'L_FOOT': foot_points, 'HEAD': head_points})
    >>> part_labels = [5, 0]

    >>> population, labels = get_population(frame_series, part_labels)

    >>> population
    array([[-45.,  66., 238.],
           [-26., -57., 249.],
           [-74., -58., 260.]])

    >>> labels
    array([0, 5, 5])

    """
    pop_list, label_list = [], []

    for index_points, label in zip(frame_series, part_labels):

        for point in index_points:

            pop_list.append(point)
            label_list.append(label)

    population, labels = np.array(pop_list), np.array(label_list)

    # Sort the labels and apply the sorting to the points
    sort_index = np.argsort(labels)
    population, labels = population[sort_index], labels[sort_index]

    return population, labels


def lengths_to_adj_list(label_connections, lengths):
    """
    Convert a sequence of lengths between body parts to an adjacency list.

    Parameters
    ----------
    label_connections : ndarray
        Each row is a connection from label A to label B.
        Column 1 is label A, column 2 is label B.
    lengths : array_like
        List of lengths between consecutive body parts
        (e.g., calf to foot).

    Returns
    -------
    label_adj_list : dict
        Adjacency list for the labels.
        label_adj_list[A][B] is the expected distance between
        a point with label A and a point with label B.

    Examples
    --------
    >>> label_connections = np.matrix('0 1; 1 2; 2 3; 3 4; 4 5; 3 5')
    >>> lengths = [62, 20, 14, 19, 20]

    >>> lengths_to_adj_list(label_connections, lengths)
    {0: {1: 62}, 1: {2: 20}, 2: {3: 14}, 3: {4: 19, 5: 39}, 4: {5: 20}, 5: {}}

    """
    last_part = label_connections.max()
    label_adj_list = {i: {} for i in range(last_part+1)}

    n_rows = len(label_connections)

    for i in range(n_rows):
        u, v = label_connections[i, 0], label_connections[i, 1]

        label_adj_list[u][v] = sum(lengths[u:v])

    return label_adj_list


def paths_to_foot(prev, dist, labels):
    """
    Retrieve the shortest path to each foot position.

    Parameters
    ----------
    prev : dict
        For each node u in the graph, prev[u] is the previous node
        on the shortest path to u.
    dist : dict
        For each node u in the graph, dist[u] is the total distance (weight)
        of the shortest path to u.
    labels : ndarray
        Label of each node.

    Returns
    -------
    path_matrix : ndarray
        One row for each foot position.
        Each row is a shortest path from head to foot.
    path_dist : ndarray
        Total distance of the path to each foot.

    Examples
    --------
    >>> prev = {0: np.nan, 1: 0, 2: 1, 3: 2, 4: 3, 5: 3}
    >>> dist = {0: 0, 1: 0, 2: 20, 3: 5, 4: 11, 5: 10}

    >>> labels = np.array([0, 1, 2, 3, 4, 4])

    >>> path_matrix, path_dist = paths_to_foot(prev, dist, labels)

    >>> path_matrix
    array([[0, 1, 2, 3, 4],
           [0, 1, 2, 3, 5]])

    >>> path_dist
    array([11., 10.])

    """
    max_label = max(labels)

    foot_index = np.where(labels == max_label)[0]
    n_feet = len(foot_index)

    path_matrix = np.full((n_feet, max_label+1), np.nan)
    path_dist = np.full(n_feet, np.nan)

    for i, foot in enumerate(foot_index):

        path_matrix[i, :] = gr.trace_path(prev, foot)
        path_dist[i] = dist[foot]

    return path_matrix.astype(int), path_dist


def get_score_matrix(population, labels, label_adj_list, score_func):
    """
    Compute a score matrix from a set of body part positions.

    Compares measured distance between points to the expected distances.

    Parameters
    ----------
    population : ndarray
        (n, 3) array of n positions.
    labels : ndarray
        (n,) array of labels for n positions.
        The labels correspond to body part types (e.g., foot).
    label_adj_list : dict
        Adjacency list for the labels.
        label_adj_list[A][B] is the expected distance between
        a point with label A and a point with label B.
    score_func : function
        Function of form f(a, b) -> c.
        Outputs a score given a measured distance and an expected distance.

    Returns
    -------
    score_matrix : ndarray
       (n, n) array of scores.

    dist_matrix : ndarray
        (n, n) array of measured distances between the n points.

    """
    # Matrix of measured distances between all n points
    dist_matrix = cdist(population, population)

    # Adjacency list of all n nodes in the graph
    # Edge weights are the expected distances between points
    label_dict = gen.iterable_to_dict(labels)
    expected_adj_list = gr.labelled_nodes_to_graph(label_dict, label_adj_list)

    # Convert adj list to a matrix so it can be compared to the
    # actual distance matrix
    expected_dist_matrix = gr.adj_list_to_matrix(expected_adj_list)

    vectorized_score_func = np.vectorize(score_func)

    # Score is high if measured distance is close to expected distance
    score_matrix = vectorized_score_func(dist_matrix, expected_dist_matrix)
    score_matrix[np.isnan(score_matrix)] = 0

    return score_matrix, dist_matrix


def pop_shortest_paths(population, labels, label_adj_list, weight_func):
    """
    Calculate shortest paths on the population of body parts.

    Parameters
    ----------
    population : ndarray
        (n, 3) array of n positions.
    labels : ndarray
        (n,) array of labels for n positions.
        The labels correspond to body part types (e.g., foot).
    label_adj_list : dict
        Adjacency list for the labels.
        label_adj_list[A][B] is the expected distance between
        a point with label A and a point with label B.
    weight_func : function
        Function used to weight edges of the graph.

    Returns
    -------
    prev : dict
        For each node u in the graph, prev[u] is the previous node
        on the shortest path to u.
    dist : dict
        For each node u in the graph, dist[u] is the total distance (weight)
        of the shortest path to u.

    """
    # Represent population as a weighted directed acyclic graph
    pop_graph = gr.points_to_graph(population, labels, label_adj_list,
                                   weight_func)

    # Run shortest path algorithm
    head_nodes = np.where(labels == 0)[0]  # Source nodes
    order = pop_graph.keys()  # Topological ordering of the nodes
    prev, dist = gr.dag_shortest_paths(pop_graph, order, head_nodes)

    return prev, dist


def filter_by_path(input_matrix, path_matrix, part_connections):
    """
    [description]

    Parameters
    ----------
    input_matrix : {[type]}
        [description]
    path_matrix : {[type]}
        [description]
    part_connections : {[type]}
        [description]

    Returns
    -------
    [type]
        [description]

    """
    filtered_matrix = np.zeros(input_matrix.shape)
    n_paths, n_path_nodes = path_matrix.shape

    for i in range(n_paths):
        for j in range(n_path_nodes):
            for k in range(n_path_nodes):

                if k in part_connections[j]:
                    # These nodes in the path are connected
                    # in the body part graph
                    a, b = path_matrix[i, j], path_matrix[i, k]
                    filtered_matrix[a, b] = input_matrix[a, b]

    return filtered_matrix


def inside_spheres(dist_matrix, point_nums, r):
    """
    Calculate which of n points are contained inside m spheres.

    Parameters
    ----------
    dist_matrix : ndarray
        (n, n) distance matrix.
        Element (i, j) is distance from point i to point j.

    point_nums : array_like
        (m, ) list of points that are the sphere centres.
        Numbers are between 1 and n.

    r : float
        Radius of spheres.

    Returns
    -------
    in_spheres : array_like
        (n, ) array of bools.
        Element i is true if point i is in the set of spheres.

    """
    n_points = len(dist_matrix)

    in_spheres = np.full(n_points, False)

    for i in point_nums:

        distances = dist_matrix[i, :]

        in_current_sphere = distances <= r
        in_spheres = in_spheres | in_current_sphere

    return in_spheres


def inside_radii(dist_matrix, path_matrix, radii):
    """
    [description]

    Parameters
    ----------
    dist_matrix : {[type]}
        [description]
    path_matrix : {[type]}
        [description]
    radii : {[type]}
        [description]

    Returns
    -------
    [type]
        [description]

    """
    in_spheres_list = []

    for path in path_matrix:
        temp = []

        for r in radii:
            in_spheres = inside_spheres(dist_matrix, path, r)
            temp.append(in_spheres)

        in_spheres_list.append(temp)

    return in_spheres_list


def select_best_feet(dist_matrix, score_matrix, path_matrix, radii):
    """
    [description]

    Parameters
    ----------
    dist_matrix : {[type]}
        [description]
    score_matrix : {[type]}
        [description]
    path_matrix : {[type]}
        [description]
    radii : {[type]}
        [description]

    Returns
    -------
    [type]
        [description]

    """
    n_paths = len(path_matrix)
    n_radii = len(radii)

    in_spheres_list = inside_radii(dist_matrix, path_matrix, radii)

    # All possible pairs of paths
    combos = list(itertools.combinations(range(n_paths), 2))

    n_combos = len(combos)

    votes, combo_scores = np.zeros(n_combos), np.zeros(n_combos)

    for i in range(n_radii):

        for ii, combo in enumerate(combos):

            in_spheres_1 = in_spheres_list[combo[0]][i]
            in_spheres_2 = in_spheres_list[combo[1]][i]

            in_spheres = in_spheres_1 | in_spheres_2

            temp = score_matrix[in_spheres, :]
            score_subset = temp[:, in_spheres]

            combo_scores[ii] = np.sum(score_subset)

        max_score = max(combo_scores)

        # Winning combos for this radius
        radius_winners = combo_scores == max_score

        # Votes go to the winners
        votes = votes + radius_winners

    winning_combo = np.argmax(votes)
    foot_1, foot_2 = combos[winning_combo]

    return foot_1, foot_2


def foot_to_pop(population, path_matrix, path_dist, foot_num_1, foot_num_2):
    """
    Return the positions comprising the shortest path to each chosen foot.

    For consistency, the two paths receive the same head position,
    which is the head along the minimum shortest path.

    Parameters
    ----------
    population : ndarray
        (n, 3) array of n positions.
    path_matrix : ndarray
        One row for each foot position.
        Each row is a shortest path from head to foot.
    path_dist : ndarray
        Total distance of the path to each foot.
    foot_num_1, foot_num_2 : int
        Numbers of foot 1 and 2 (out of all foot positions)

    Returns
    -------
    pop_1, pop_2 : ndarray
        (n_labels, 3) array of chosen points from the input population.
        One point for each label (i.e., each body part type).

    """
    path_1, path_2 = path_matrix[foot_num_1, :], path_matrix[foot_num_2, :]
    pop_1, pop_2 = population[path_1, :], population[path_2, :]

    # Select the head along the minimum shortest path
    min_path = path_matrix[np.argmin(path_dist), :]
    head_pos = population[min_path[0], :]

    pop_1[0, :], pop_2[0, :] = head_pos, head_pos

    return pop_1, pop_2


def process_frame(population, labels, label_adj_list, radii, cost_func,
                  score_func):
    """
    Return chosen body part positions from an input set of position hypotheses.

    Use a score function to select the best foot positions,
    and return the shortest paths to these feet in the body part graph.

    Parameters
    ----------
    population : ndarray
        (n, 3) array of n positions.
    labels : ndarray
        (n,) array of labels for n positions.
        The labels correspond to body part types (e.g., foot).
    label_adj_list : dict
        Adjacency list for the labels.
        label_adj_list[A][B] is the expected distance between
        a point with label A and a point with label B.
    radii : array_like
        List of radii used to select the best feet.
    cost_func : function
        Cost function used to weight the body part graph.
    score_func : function
        Score function used to assign scores to connections between body parts.

    Returns
    -------
    pop_1, pop_2 : ndarray
        (n_labels, 3) array of chosen points from the input population.
        One point for each label (i.e., each body part type)

    """
    cons_label_adj_list = only_consecutive_labels(label_adj_list)

    prev, dist = pop_shortest_paths(population, labels,
                                    cons_label_adj_list, cost_func)

    # Get shortest path to each foot
    path_matrix, path_dist = paths_to_foot(prev, dist, labels)

    score_matrix, dist_matrix = get_score_matrix(population, labels,
                                                 label_adj_list, score_func)

    filtered_score_matrix = filter_by_path(score_matrix, path_matrix,
                                           label_adj_list)

    foot_1, foot_2 = select_best_feet(dist_matrix, filtered_score_matrix,
                                      path_matrix, radii)

    pop_1, pop_2 = foot_to_pop(population, path_matrix, path_dist,
                               foot_1, foot_2)

    return pop_1, pop_2


def direction_of_pass(df_pass):
    """
    Return vector representing overall direction of motion for a walking pass.

    Parameters
    ----------
    df_pass : DataFrame
        Head and foot positions at each frame in a walking pass.
        Three columns: HEAD, L_FOOT, R_FOOT.

    Returns
    -------
    line_point : ndarray
        Point that lies on line of motion.
    direction_pass : ndarray
        Direction of motion for the walking pass.

    """
    # All head positions on one walking pass
    head_points = np.stack(tuple(df_pass.HEAD))

    # Line of best fit for head positions
    line_point, direction_pass = lin.best_fit_line(head_points)

    return line_point, direction_pass


def verify_sides(foot_l, foot_r, head, direction_motion):
    """
    Verify that the assigned feet are consistent with the direction of motion.

    Parameters
    ----------
    foot_l, foot_r : ndarray
        Left and right foot positions.
    head : ndarray
        Head position
    direction_motion : array_like
        Direction of motion

    Returns
    -------
    verified : bool
        True if the foot labels are consistent with the direction of motion.

    Examples
    --------
    >>> direction = [1, 0, 0]
    >>> foot_l, foot_r = np.array([88, -67, 267]), np.array([34, -66, 225])
    >>> head = np.array([70, 57, 249])

    >>> verify_sides(foot_l, foot_r, head, direction)
    True

    >>> verify_sides(foot_r, foot_l, head, direction)
    False

    >>> verify_sides(foot_l, foot_r, head, -np.array(direction))
    False

    >>> verify_sides(foot_r, foot_l, head, -np.array(direction))
    True

    """
    mean_foot = (foot_l + foot_r) / 2
    up = head - mean_foot

    vector_to_left = foot_l - mean_foot

    angle_dir = lin.target_side(direction_motion, up, vector_to_left)

    verified = angle_dir == 'left' or angle_dir == 'straight'

    return verified


def verify_sides_pass(df_pass, direction_pass):
    """
    Verify the assigned foot sides on each frame in a walking pass.

    Parameters
    ----------
    df_pass : DataFrame
        Head and foot positions at each frame in a walking pass.
        Three columns: HEAD, L_FOOT, R_FOOT.
    direction_pass : array_like
        Direction of motion for walking pass.

    Yields
    ------
    bool
        True if sides are verified.

    """
    for frame, row in df_pass.iterrows():

        yield verify_sides(row.L_FOOT, row.R_FOOT, row.HEAD, direction_pass)


def evaluate_foot_side(head_points, foot_points_1, foot_points_2):
    """
    Yield a value indicating the side (left/right) of a foot.

    A positive value indicates right, while negative indicates left.

    Parameters
    ----------
    head_points : ndarray
        (n, 3) array of head positions.
    foot_points_1 : ndarray
        (n, 3) array of foot positions.

    Yields
    ------
    float
        Value indicating left/right direction for foot 1.

    """
    _, direction = lin.best_fit_line(head_points)

    for head, foot_1, foot_2 in zip(head_points, foot_points_1, foot_points_2):

        mean_foot = (foot_1 + foot_2) / 2
        up = head - mean_foot

        target = foot_1 - mean_foot

        yield lin.target_side_value(direction, up, target)


def enforce_consistency(df_pass, verified_sides):
    """
    Assign foot positions to correct left/right sides.

    Parameters
    ----------
    df_pass : DataFrame
        Head and foot positions at each frame in a walking pass.
        Three columns: HEAD, L_FOOT, R_FOOT.
    verified_sides : array_like
        Element is True if the corresponding frame has correct sides.

    Returns
    -------
    df_consistent : DataFrame
        DataFrame with feet on consistent sides.

    """
    df_consistent = df_pass.copy()

    for i, (frame, row) in enumerate(df_consistent.iterrows()):

        if not verified_sides[i]:
            # The sides should be switched.

            row.L_FOOT, row.R_FOOT = row.R_FOOT, row.L_FOOT
            df_consistent.loc[frame] = row

    return df_consistent
