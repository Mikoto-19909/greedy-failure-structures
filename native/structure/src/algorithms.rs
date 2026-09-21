use crate::bitsets::{cover, decode_masks, marginal};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::cmp::Reverse;
use std::collections::BinaryHeap;

type LazyRun = (Vec<(usize, usize, usize)>, usize, usize);

fn check_budget(k: usize, set_count: usize) -> PyResult<()> {
    if k == 0 || k > set_count {
        return Err(PyValueError::new_err(
            "k must be between 1 and the number of sets",
        ));
    }
    Ok(())
}

/// Full scan with input-index tie breaking, including zero-gain selections.
#[pyfunction]
pub(crate) fn greedy(
    masks: Vec<Vec<u8>>,
    universe_size: usize,
    k: usize,
) -> PyResult<(Vec<usize>, usize)> {
    let words = decode_masks(&masks, universe_size)?;
    check_budget(k, words.len())?;
    let mut covered = vec![0; words[0].len()];
    let mut available = vec![true; words.len()];
    let mut selected = Vec::with_capacity(k);
    let mut evaluations = 0;
    for _ in 0..k {
        let mut best = None;
        let mut best_gain = 0;
        for (index, mask) in words.iter().enumerate() {
            if available[index] {
                evaluations += 1;
                let gain = marginal(mask, &covered);
                if best.is_none() || gain > best_gain {
                    best = Some(index);
                    best_gain = gain;
                }
            }
        }
        let index = best.expect("validated budget leaves an available candidate");
        selected.push(index);
        available[index] = false;
        cover(&mut covered, &words[index]);
    }
    Ok((selected, evaluations))
}

/// Refresh the largest upper bound; equal gains favor the smallest input index.
#[pyfunction]
pub(crate) fn lazy_greedy(
    masks: Vec<Vec<u8>>,
    universe_size: usize,
    k: usize,
) -> PyResult<LazyRun> {
    let words = decode_masks(&masks, universe_size)?;
    check_budget(k, words.len())?;
    let mut covered = vec![0; words[0].len()];
    let mut queue: BinaryHeap<(usize, Reverse<usize>)> = words
        .iter()
        .enumerate()
        .map(|(index, mask)| (marginal(mask, &covered), Reverse(index)))
        .collect();
    let mut evaluations = words.len();
    let mut pops = 0;
    let mut trajectory = Vec::with_capacity(k);
    for _ in 0..k {
        loop {
            let (_, Reverse(index)) = queue
                .pop()
                .expect("validated budget leaves a queued candidate");
            pops += 1;
            evaluations += 1;
            let gain = marginal(&words[index], &covered);
            let refreshed = (gain, Reverse(index));
            if queue.peek().is_none_or(|best| refreshed >= *best) {
                cover(&mut covered, &words[index]);
                trajectory.push((index, gain, evaluations));
                break;
            }
            queue.push(refreshed);
        }
    }
    Ok((trajectory, evaluations, pops))
}
