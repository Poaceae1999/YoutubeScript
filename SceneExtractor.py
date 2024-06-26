# SceneExtractor
import torch.nn.functional as F
import cv2
import numpy as np
import os
import torch
from torchvision import models, transforms
from collections import OrderedDict
from logger import logger

# Initialize ResNet50 model, only keep up to the average pooling layer
base_model = models.resnet50(pretrained=True)
base_model = torch.nn.Sequential(*(list(base_model.children())[:-1]))
base_model.eval()


def extract_features(frame):
    """
    Extracts features from a given frame.

    Args:
        frame (numpy.ndarray): The input frame.

    Returns:
        numpy.ndarray: The extracted features.
    """
    img = cv2.resize(frame, (224, 224))

    # Convert to float tensor
    x = torch.from_numpy(img).float()

    # Reshape to (channels, height, width) and normalize
    x = x.permute(2, 0, 1) / 255.0
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    x = (x - mean) / std

    with torch.no_grad():
        features = base_model(x)
    return features.numpy()


def process_frame(frame_number, frame):
    features = extract_features(frame)
    return frame_number, features


def calculate_similarities_parallel(video_path):
    """
    Calculate similarities between frames in a video using parallel processing.

    Args:
        video_path (str): The path to the video file.

    Returns:
        list: A list of tuples containing the frame number and similarity score.

    """
    cap = cv2.VideoCapture(video_path)
    features_dict = OrderedDict()
    logger.debug(f"to threadPool in similarity calculation")

    last_processed_timestamp = -1.0  # Initialize to a negative value

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000  # Get timestamp in seconds

        if (
            timestamp - last_processed_timestamp >= 1.0
        ):  # Check if at least 1 second has passed
            timestamp, features = process_frame(timestamp, frame)
            if features is not None:
                features_dict[int(timestamp)] = features
            last_processed_timestamp = timestamp  # Update the last processed timestamp

    logger.debug(f"features len :{len(features_dict)}")

    # Calculate similarities after all futures have completed
    similarities = []
    last_features = None

    for frame_number, features in sorted(features_dict.items()):
        if last_features is not None:
            # Flatten the feature vectors to 1D
            features = features.reshape(-1)
            last_features = last_features.reshape(-1)

            # Use PyTorch's cosine_similarity function
            sim = F.cosine_similarity(
                torch.from_numpy(features), torch.from_numpy(last_features), dim=0
            )

            # Convert the similarity to a float
            similarities.append((frame_number, sim.item()))
        last_features = features
    cap.release()
    return similarities


def detect_scene_changes(video_path, alpha=0, frame_per_minute=0):
    """
    Detects scene changes in a video based on similarity scores between frames.

    Args:
        video_path (str): The path to the video file.
        alpha (float, optional): The number of standard deviations below the mean similarity score
            to consider as a scene change. Defaults to 0.
        frame_per_minute (float, optional): The number of frames per minute to consider as a scene change.
            Defaults to 0.

    Returns:
        list: A list of time points (in seconds) where scene changes occur.

    Raises:
        AssertionError: If the video_path does not exist, alpha is not a number, or frame_per_minute is not a number.
        AssertionError: If the similarities list is empty or the similarity_scores list is empty.
    """
    
    assert os.path.isfile(video_path), f"{video_path} does not exist"
    assert isinstance(alpha, (int, float)), "alpha must be a number"
    assert isinstance(
        frame_per_minute, (int, float)
    ), "frame_per_minute must be a number"

    logger.debug(f"video_path:{video_path}")

    similarities = calculate_similarities_parallel(video_path)
    logger.debug(f"similarities:{similarities}")

    assert similarities, "similarities is empty"

    similarity_scores = [sim for _, sim in similarities]
    assert similarity_scores, "similarity_scores is empty"

    mean_sim = np.mean(similarity_scores)
    std_sim = np.std(similarity_scores)
    threshold = mean_sim - alpha * std_sim
    logger.debug(f"similarity_scores:{similarity_scores}")
    percentile = np.percentile(
        similarity_scores, round(1 / 60 * 100 * frame_per_minute)
    )
    scene_changes = []
    logger.debug(f"scene threshold:{threshold}")
    for frame_number, sim in similarities:
        if sim <= threshold:
            time_in_seconds = frame_number
            scene_changes.append(time_in_seconds)
        elif sim <= percentile:
            time_in_seconds = frame_number
            scene_changes.append(time_in_seconds)
    return scene_changes
