"""In-memory shuffle cycles; never enumerate or open source media."""
import random


def reshuffle_cycle(paths, previous, rng=random):
    """Prepare a complete new pass without repeating the item just selected."""
    if len(paths)<2:return
    rng.shuffle(paths)
    if paths[0]==previous:
        alternatives=[index for index,path in enumerate(paths) if path!=previous]
        if alternatives:
            index=rng.choice(alternatives)
            paths[0],paths[index]=paths[index],paths[0]
