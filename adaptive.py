# Adaptive difficulty engine

def adjust_difficulty(current_level, last_score):
    """
    Increase difficulty if student is correct, decrease if incorrect.
    Difficulty can map to scene index or hints.
    """
    if last_score == 'correct':
        return min(current_level + 1, 5)
    elif last_score == 'incorrect':
        return max(current_level - 1, 1)
    else:
        return current_level
