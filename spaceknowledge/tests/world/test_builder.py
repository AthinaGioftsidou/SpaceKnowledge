"""Tests for DestinationBuilder."""

import unittest

from spaceknowledge.world.builder import DestinationBuilder
from spaceknowledge.world.item import PlainItem


def a_key() -> PlainItem:
    return PlainItem("brass_key", "brass key", "a small brass key")


class TestBuildingADestination(unittest.TestCase):
    def test_a_named_destination_builds(self) -> None:
        destination = DestinationBuilder("hall").named("Entrance Hall").build()
        self.assertEqual("Entrance Hall", destination.name)

    def test_the_calls_chain_in_any_order(self) -> None:
        # Each fluent method returns the builder, so order is the caller's
        # choice. That is the property that makes the pattern readable.
        destination = (
            DestinationBuilder("hall")
            .described("Cold and tiled.")
            .holding(a_key())
            .named("Entrance Hall")
            .build()
        )
        self.assertEqual("Entrance Hall", destination.name)
        self.assertIsNotNone(destination.find_item("brass_key"))

    def test_items_arrive_in_the_destination(self) -> None:
        destination = DestinationBuilder("hall").named("Hall").holding(a_key()).build()
        self.assertEqual(1, destination.item_count())

    def test_an_empty_destination_id_is_refused_at_the_start(self) -> None:
        # Refused when the builder is made, not when build() is called, so the
        # failure lands at the call site that got it wrong.
        with self.assertRaises(ValueError):
            DestinationBuilder("")


class TestTheBuilderRefusesToProduceSomethingUnusable(unittest.TestCase):
    def test_a_destination_that_was_never_named_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            DestinationBuilder("hall").described("Cold.").build()

    def test_a_builder_is_single_use(self) -> None:
        # A reused builder would give the second destination the first destination's items.
        # Refusing is one line and the alternative is a bug nobody can see.
        builder = DestinationBuilder("hall").named("Hall").holding(a_key())
        builder.build()
        with self.assertRaises(ValueError):
            builder.build()


class TestArgumentTypes(unittest.TestCase):
    def test_a_string_is_refused_where_a_class_is_expected(self) -> None:
        # Python does not enforce an annotation, so the method checks it.
        bad = "not an object"
        calls = [
            ("holding item", lambda: DestinationBuilder("hall").holding(bad)),
        ]
        for label, call in calls:
            with self.subTest(label):
                with self.assertRaisesRegex(TypeError, "must be"):
                    call()


if __name__ == "__main__":
    unittest.main()
