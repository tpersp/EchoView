from collections import Counter
import random
from echoview.playlist import reshuffle_cycle


def test_each_pass_contains_every_item_once_and_boundaries_do_not_repeat():
    paths=[f'folder-{i//100}/gif-{i}.gif' for i in range(300)]
    expected=Counter(paths);rng=random.Random(42);previous=None;orders=[]
    for _ in range(20):
        reshuffle_cycle(paths,previous,rng)
        assert Counter(paths)==expected
        assert paths[0]!=previous
        orders.append(tuple(paths))
        previous=paths[-1]
    assert len(set(orders))==20


def test_boundary_collision_is_corrected_without_dropping_items():
    class Forced:
        def shuffle(self,paths):paths[:]=['last','first','middle']
        def choice(self,values):return values[-1]
    paths=['first','middle','last']
    reshuffle_cycle(paths,'last',Forced())
    assert paths==['middle','first','last']


def test_empty_singleton_and_duplicate_only_lists_are_safe():
    for paths in ([],['one'],['one','one']):
        before=list(paths);reshuffle_cycle(paths,'one',random.Random(1))
        assert paths==before
