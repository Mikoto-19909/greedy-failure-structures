"""Fault-path checks for the local optional backend."""
import unittest
from unittest.mock import patch
from pipeline_backends import Backend, all_budget_optima


class BackendFailureTests(unittest.TestCase):
    def test_cuda_runtime_failure_falls_back_with_exact_witnesses(self):
        import cupy
        backend = Backend('hybrid')
        backend.cp = cupy
        batch = [[3] * 20]
        with patch.object(backend, 'gpu', side_effect=cupy.cuda.runtime.CUDARuntimeError(2)):
            result = backend(batch)
        self.assertEqual(result, [all_budget_optima(batch[0])])
        self.assertEqual(backend.events[-1]['selected'], 'compiled')
        self.assertIn('CUDARuntimeError', backend.events[-1]['fallback'])

    def test_unexpected_algorithm_error_is_not_hidden_by_fallback(self):
        backend = Backend('hybrid')
        with patch.object(backend, 'gpu', side_effect=ValueError('injected logic defect')):
            with self.assertRaisesRegex(ValueError, 'logic defect'):
                backend([[3]*20])
        self.assertEqual(backend.events, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
