import unittest
from celery import Celery
from celery.app.task import Task
from celery.canvas import chain
from collections import namedtuple
from firexkit.task import FireXTask, get_attr_unwrapped
from firexkit.chain import ReturnsCodingException, returns, verify_chain_arguments, InvalidChainArgsException, \
    InjectArgs
from functools import wraps


class ReturnsTests(unittest.TestCase):

    def test_returns_normal_case(self):
        test_app = Celery()

        @test_app.task(base=FireXTask)
        @returns("stuff")
        def a_task(the_goods):
            return the_goods

        ret = a_task(the_goods="the_goods")
        self.assertTrue(type(ret) is dict)
        self.assertTrue(len(ret) == 2)
        self.assertTrue("stuff" in ret)
        self.assertTrue("the_goods" in ret)
        self.assertEqual("the_goods", ret["the_goods"])
        self.assertEqual(ret["stuff"], ret["the_goods"])

    def test_bad_returns_code(self):
        test_app = Celery()

        # duplicate keys
        with self.assertRaises(ReturnsCodingException):
            @test_app.task(base=FireXTask)
            @returns("a", "a")
            def a_task():
                # Should not reach here
                pass  # pragma: no cover

        # @returns above @app.task
        with self.assertRaises(ReturnsCodingException):
            @returns("a")
            @test_app.task(base=FireXTask)
            def a_task():
                # Should not reach here
                pass  # pragma: no cover

        # no keys in @returns
        with self.assertRaises(ReturnsCodingException):
            @test_app.task(base=FireXTask)
            @returns()
            def a_task():
                # Should not reach here
                pass  # pragma: no cover

        # No actual return
        with self.assertRaises(ReturnsCodingException):
            @test_app.task(base=FireXTask)
            @returns("a", "b")
            def a_task():
                return
            a_task()

        # values returned don't match keys
        with self.assertRaises(ReturnsCodingException):
            @test_app.task(base=FireXTask)
            @returns("a", "b")
            def another_task():
                return None, None, None
            another_task()

    def test_returns_and_bind(self):
        test_app = Celery()

        @test_app.task(base=FireXTask, bind=True)
        @returns("the_task_name", "stuff")
        def a_task(task_self, the_goods):
            return task_self.name, the_goods

        ret = a_task(the_goods="the_goods")
        self.assertTrue(type(ret) is dict)
        self.assertTrue(len(ret) == 3)
        self.assertTrue("stuff" in ret)
        self.assertTrue("the_task_name" in ret)
        self.assertTrue("the_goods" in ret)
        # noinspection PyTypeChecker
        self.assertEqual("the_goods", ret["the_goods"])
        # noinspection PyTypeChecker
        self.assertEqual(ret["stuff"], ret["the_goods"])

    def test_returns_play_nice_with_decorators(self):
        test_app = Celery()

        def passing_through(func):
            @wraps(func)
            def inner(*args, **kwargs):
                return func(*args, **kwargs)
            return inner

        @test_app.task(base=FireXTask)
        @returns("stuff")
        @passing_through
        def a_task(the_goods):
            return the_goods

        ret = a_task(the_goods="the_goods")
        self.assertTrue(type(ret) is dict)
        self.assertTrue(len(ret) == 2)
        self.assertTrue("stuff" in ret)

    def test_returning_named_tuples(self):
        test_app = Celery()
        TestingTuple = namedtuple('TestingTuple', ['thing1', 'thing2'])

        @test_app.task(base=FireXTask)
        @returns("named_t")
        def a_task():
            return TestingTuple(thing1=1, thing2="two")
        ret = a_task()

        # noinspection PyTypeChecker
        self.assertTrue(type(ret["named_t"]) is TestingTuple)
        self.assertTrue(type(ret) is dict)
        self.assertTrue(len(ret) == 1)
        self.assertTrue("named_t" in ret)

        # noinspection PyTypeChecker
        self.assertEqual(1, ret["named_t"].thing1)
        # noinspection PyTypeChecker
        self.assertEqual("two", ret["named_t"].thing2)


class ChainVerificationTests(unittest.TestCase):

    def test_interoperability_with_regular_celery_tasks(self):
        test_app = Celery()

        @test_app.task(base=Task)
        @returns("stuff")
        def task1a():
            return "the_stuff"  # pragma: no cover

        @test_app.task(base=Task)
        def task2a(stuff):
            assert stuff  # pragma: no cover

        @test_app.task(base=FireXTask)
        @returns("stuff")
        def task1b():
            return "the_stuff"  # pragma: no cover

        @test_app.task(base=FireXTask)
        def task2b(stuff):
            assert stuff  # pragma: no cover

        with self.subTest("Celery to Celery"):
            c = chain(task1a.s(), task2a.s())
            verify_chain_arguments(c)

        with self.subTest("FireX to Celery"):
            c = chain(task1b.s(), task2b.s())
            verify_chain_arguments(c)

        with self.subTest("Celery to FireX"):
            c = chain(task1a.s(), task2b.s())
            verify_chain_arguments(c)

    def test_detect_missing(self):
        test_app = Celery()

        @test_app.task(base=FireXTask)
        def task1():
            pass  # pragma: no cover

        @test_app.task(base=FireXTask)
        def task2raise(stuff):
            assert stuff  # pragma: no cover

        @test_app.task(base=FireXTask)
        def task2ok(stuff=None):
            assert stuff  # pragma: no cover

        # fails if it is missing something
        c = chain(task1.s(), task2raise.s())
        with self.assertRaises(InvalidChainArgsException):
            verify_chain_arguments(c)

        # same result a second time
        with self.assertRaises(InvalidChainArgsException):
            verify_chain_arguments(c)

        # pass if it gets what it needs
        c = chain(task1.s(stuff="yes"), task2raise.s())
        verify_chain_arguments(c)

        # default arguments are sufficient
        c = chain(task1.s(), task2ok.s())
        verify_chain_arguments(c)

    def test_indirect(self):
        test_app = Celery()

        @test_app.task(base=FireXTask)
        @returns("stuff")
        def task1_with_return():
            pass  # pragma: no cover

        # noinspection PyUnusedLocal
        @test_app.task(base=FireXTask)
        def task2needs(thing="@stuff"):
            pass  # pragma: no cover

        c = chain(task1_with_return.s(), task2needs.s())
        verify_chain_arguments(c)

        @test_app.task(base=FireXTask)
        def task1_no_return():
            pass  # pragma: no cover

        c = chain(task1_no_return.s(stuff="yep"), task2needs.s())
        verify_chain_arguments(c)

        # todo: add this check to the validation
        # with self.assertRaises(InvalidChainArgsException):
        #     c = chain(task1_no_return.s(), task2needs.s())
        #     verify_chain_arguments(c)

        with self.assertRaises(InvalidChainArgsException):
            c = chain(task1_no_return.s(thing="@stuff"), task2needs.s())
            verify_chain_arguments(c)

        with self.assertRaises(InvalidChainArgsException):
            c = chain(task1_no_return.s(), task2needs.s(thing="@stuff"))
            verify_chain_arguments(c)

    def test_arg_properties(self):
        test_app = Celery()

        # noinspection PyUnusedLocal
        @test_app.task(base=FireXTask)
        @returns("take_this")
        def a_task(required, optional="yup"):
            pass  # pragma: no cover

        self.assertEqual(a_task.optional_args, {'optional': "yup"})
        self.assertEqual(a_task.required_args, ['required'])
        self.assertEqual(a_task.return_keys, ('take_this',))
        self.assertEqual(a_task.optional_args, {'optional': "yup"})  # repeat

    def test_chain_assembly_validation(self):
        test_app = Celery()

        # noinspection PyUnusedLocal
        @test_app.task(base=FireXTask)
        @returns("final")
        def beginning(start):
            return "pass"  # pragma: no cover

        @test_app.task(base=FireXTask)
        @returns("mildly_amusing")
        def middle_task(very_important):
            assert very_important  # pragma: no cover

        @test_app.task(base=FireXTask)
        @returns("finished")
        def ending(final, missing):
            assert final, missing  # pragma: no cover

        with self.assertRaises(InvalidChainArgsException):
            c = beginning.s(start="something") | middle_task.s(very_important="oh_it_is") | ending.s()
            verify_chain_arguments(c)

        c = beginning.s(start="something") | middle_task.s(very_important="oh_it_is") | ending.s(missing="not_missing")
        verify_chain_arguments(c)
        self.assertIsNotNone(chain)

        with self.assertRaises(InvalidChainArgsException):
            c2 = beginning.s(start="something") | middle_task.s(very_important="@not_there") | ending.s(
                missing="not missing")
            verify_chain_arguments(c2)

        c2 = beginning.s(start="something") | middle_task.s(very_important="@final") | ending.s(missing="not missing")
        verify_chain_arguments(c2)
        self.assertIsNotNone(c2)


class TaskUtilTests(unittest.TestCase):
    def test_get_attr_unwrapped(self):
        with self.subTest("Raise error"):
            test_app = Celery()

            @test_app.task(base=Task)
            def fun():
                pass  # pragma: no cover
            with self.assertRaises(AttributeError):
                get_attr_unwrapped(fun, "_out")

            self.assertEqual(get_attr_unwrapped(fun, "_out", "yes"), "yes")
            self.assertEqual(get_attr_unwrapped(fun, "_out", None), None)  # special case

        with self.subTest("Find attribute"):
            test_app = Celery()

            @test_app.task(base=Task)
            @returns("stuff")
            def fun():
                pass  # pragma: no cover
            self.assertEqual(get_attr_unwrapped(fun, "_out"), {"stuff"})


class InjectArgsTest(unittest.TestCase):
    def test_inject_irrelevant(self):
        test_app = Celery()

        @test_app.task(base=FireXTask)
        def injected_task1():
            pass  # pragma: no cover

        # inject unneeded things
        with self.subTest("Inject nothing"):
            kwargs = {}
            c = InjectArgs(**kwargs)
            c = c | injected_task1.s()
            verify_chain_arguments(c)

        with self.subTest("Inject nothing useful"):
            kwargs = {"random": "thing"}
            c = InjectArgs(**kwargs)
            c = c | injected_task1.s()
            verify_chain_arguments(c)

    def test_inject_necessary(self):
        test_app = Celery()

        # noinspection PyUnusedLocal
        @test_app.task(base=FireXTask)
        def injected_task2(needed):
            pass  # pragma: no cover

        with self.subTest("Inject directly"):
            c = InjectArgs(needed='stuff', **{})
            c = c | injected_task2.s()
            verify_chain_arguments(c)

        kwargs = {"needed": "thing"}
        with self.subTest("Inject with kwargs"):
            c = InjectArgs(not_needed='stuff', **kwargs)
            c = c | injected_task2.s()
            verify_chain_arguments(c)

        @test_app.task(base=FireXTask)
        def injected_task3():
            pass  # pragma: no cover

        with self.subTest("Injected chained with another"):
            c = InjectArgs(**kwargs)
            c |= injected_task3.s()
            c = chain(c, injected_task2.s())
            verify_chain_arguments(c)

        with self.subTest("Inject into existing chain"):
            c = InjectArgs(**kwargs)
            n_c = injected_task3.s() | injected_task2.s()
            c = c | n_c
            verify_chain_arguments(c)

        with self.subTest("Inject into existing chain"):
            c = InjectArgs(**kwargs)
            c = c | (injected_task3.s() | injected_task2.s())
            verify_chain_arguments(c)

        with self.subTest("Inject into Another inject"):
            c = InjectArgs(**kwargs)
            c |= InjectArgs(sleep=None)
            c |= injected_task2.s()


class LabelTests(unittest.TestCase):
    def test_labels(self):
        test_app = Celery()

        @test_app.task(base=FireXTask)
        def task1():
            pass  # pragma: no cover

        @test_app.task(base=FireXTask)
        def task2():
            pass  # pragma: no cover

        with self.subTest('InjectArgs with one task and default label'):
            c = InjectArgs() | task1.s()
            self.assertEqual(c.get_label(), task1.name)

        with self.subTest('One Task with default label'):
            c = task1.s()
            self.assertEqual(c.get_label(), task1.name)

        with self.subTest('Two Tasks with default label'):
            c = task1.s() | task2.s()
            self.assertEqual(c.get_label(), '|'.join([task1.name, task2.name]))

        with self.subTest('InjectArgs with one task and label'):
            c = InjectArgs() | task1.s()
            label = 'something'
            c.set_label(label)
            self.assertEqual(c.get_label(), label)

        with self.subTest('One task with label'):
            c = task1.s()
            label = 'something'
            c.set_label(label)
            self.assertEqual(c.get_label(), label)

        with self.subTest('Two tasks with label'):
            c = task1.s() | task2.s()
            label = 'something'
            c.set_label(label)
            self.assertEqual(c.get_label(), label)
