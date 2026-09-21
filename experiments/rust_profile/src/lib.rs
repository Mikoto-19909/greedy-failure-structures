//! Diagnostic copy of the frozen kernels. Never imported by production maxcover.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyBytesMethods};
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashSet};
use std::time::Instant;

type Counts = (Vec<usize>, Vec<(usize, usize)>, usize);
type LazyRun = (Vec<(usize, usize, usize)>, usize, usize);

fn decode(masks: &[Vec<u8>], n: usize) -> PyResult<Vec<Vec<u64>>> {
    if n == 0 || masks.is_empty() {
        return Err(PyValueError::new_err(
            "positive universe and candidates required",
        ));
    }
    let width = n.div_ceil(8);
    let tail = n % 8;
    if masks
        .iter()
        .any(|m| m.len() != width || (tail != 0 && m[width - 1] >> tail != 0))
    {
        return Err(PyValueError::new_err("invalid mask"));
    }
    Ok(masks
        .iter()
        .map(|m| {
            m.chunks(8)
                .map(|part| {
                    let mut bytes = [0; 8];
                    bytes[..part.len()].copy_from_slice(part);
                    u64::from_le_bytes(bytes)
                })
                .collect()
        })
        .collect())
}

fn counts_words(words: &[Vec<u64>], n: usize) -> (Counts, [u64; 3]) {
    let start = Instant::now();
    let mut frequencies = vec![0; n];
    for mask in words {
        for (index, &word) in mask.iter().enumerate() {
            let mut remaining = word;
            while remaining != 0 {
                frequencies[index * 64 + remaining.trailing_zeros() as usize] += 1;
                remaining &= remaining - 1;
            }
        }
    }
    let frequency_ns = start.elapsed().as_nanos() as u64;
    let start = Instant::now();
    let mut pairs = Vec::new();
    for (index, left) in words.iter().enumerate() {
        for right in &words[index + 1..] {
            let (mut intersection, mut union) = (0, 0);
            for (&a, &b) in left.iter().zip(right) {
                intersection += (a & b).count_ones() as usize;
                union += (a | b).count_ones() as usize;
            }
            if union != 0 {
                pairs.push((intersection, union));
            }
        }
    }
    let pair_ns = start.elapsed().as_nanos() as u64;
    let start = Instant::now();
    let mut seen = HashSet::new();
    let unique: Vec<&Vec<u64>> = words.iter().filter(|mask| seen.insert(*mask)).collect();
    let dominated = unique
        .iter()
        .filter(|&&mask| {
            unique
                .iter()
                .any(|&other| mask != other && mask.iter().zip(other).all(|(&a, &b)| a & b == a))
        })
        .count();
    (
        (frequencies, pairs, dominated),
        [frequency_ns, pair_ns, start.elapsed().as_nanos() as u64],
    )
}

fn lazy_words(words: &[Vec<u64>], k: usize) -> PyResult<(LazyRun, [u64; 2])> {
    if k == 0 || k > words.len() {
        return Err(PyValueError::new_err("invalid budget"));
    }
    let start = Instant::now();
    let mut covered = vec![0u64; words[0].len()];
    let gain = |mask: &[u64], covered: &[u64]| {
        mask.iter()
            .zip(covered)
            .map(|(&a, &b)| (a & !b).count_ones() as usize)
            .sum::<usize>()
    };
    let mut queue: BinaryHeap<(usize, Reverse<usize>)> = words
        .iter()
        .enumerate()
        .map(|(i, m)| (gain(m, &covered), Reverse(i)))
        .collect();
    let queue_ns = start.elapsed().as_nanos() as u64;
    let start = Instant::now();
    let (mut evaluations, mut pops) = (words.len(), 0);
    let mut trace = Vec::with_capacity(k);
    for _ in 0..k {
        loop {
            let (_, Reverse(index)) = queue.pop().expect("valid budget");
            pops += 1;
            evaluations += 1;
            let marginal = gain(&words[index], &covered);
            let refreshed = (marginal, Reverse(index));
            if queue.peek().is_none_or(|best| refreshed >= *best) {
                for (seen, &word) in covered.iter_mut().zip(&words[index]) {
                    *seen |= word;
                }
                trace.push((index, marginal, evaluations));
                break;
            }
            queue.push(refreshed);
        }
    }
    Ok((
        (trace, evaluations, pops),
        [queue_ns, start.elapsed().as_nanos() as u64],
    ))
}

#[pyfunction]
fn counts_profile(masks: Vec<Vec<u8>>, n: usize) -> PyResult<(Counts, [u64; 4])> {
    let start = Instant::now();
    let words = decode(&masks, n)?;
    let decode_ns = start.elapsed().as_nanos() as u64;
    let (counts, stages) = counts_words(&words, n);
    Ok((counts, [decode_ns, stages[0], stages[1], stages[2]]))
}

#[pyfunction]
fn lazy_profile(masks: Vec<Vec<u8>>, n: usize, k: usize) -> PyResult<(LazyRun, [u64; 3])> {
    let start = Instant::now();
    let words = decode(&masks, n)?;
    let decode_ns = start.elapsed().as_nanos() as u64;
    let (run, stages) = lazy_words(&words, k)?;
    Ok((run, [decode_ns, stages[0], stages[1]]))
}

/// Experimental transport only: keep the same integer counts and pair order.
#[pyfunction]
fn counts_packed(masks: Vec<Vec<u8>>, n: usize) -> PyResult<(Vec<usize>, Vec<u8>, usize)> {
    let words = decode(&masks, n)?;
    let ((frequencies, pairs, dominated), _) = counts_words(&words, n);
    let mut packed = Vec::with_capacity(pairs.len() * 16);
    for (intersection, union) in pairs {
        packed.extend_from_slice(&(intersection as u64).to_le_bytes());
        packed.extend_from_slice(&(union as u64).to_le_bytes());
    }
    Ok((frequencies, packed, dominated))
}

#[pyfunction]
fn ingest_owned(masks: Vec<Vec<u8>>) -> usize {
    std::hint::black_box(masks).len()
}

#[pyfunction]
fn ingest_borrowed(masks: Vec<Bound<'_, PyBytes>>) -> usize {
    std::hint::black_box(masks.iter().map(|m| m.as_bytes().len()).sum())
}

#[pyclass]
struct Prepared {
    words: Vec<Vec<u64>>,
    n: usize,
}

#[pymethods]
impl Prepared {
    #[new]
    fn new(masks: Vec<Vec<u8>>, n: usize) -> PyResult<Self> {
        Ok(Self {
            words: decode(&masks, n)?,
            n,
        })
    }
    fn lazy(&self, k: usize) -> PyResult<LazyRun> {
        Ok(lazy_words(&self.words, k)?.0)
    }
    fn counts(&self) -> Counts {
        counts_words(&self.words, self.n).0
    }
}

#[pymodule]
fn maxcover_profile_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(counts_profile, module)?)?;
    module.add_function(wrap_pyfunction!(lazy_profile, module)?)?;
    module.add_function(wrap_pyfunction!(counts_packed, module)?)?;
    module.add_function(wrap_pyfunction!(ingest_owned, module)?)?;
    module.add_function(wrap_pyfunction!(ingest_borrowed, module)?)?;
    module.add_class::<Prepared>()?;
    Ok(())
}
