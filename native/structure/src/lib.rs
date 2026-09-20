mod algorithms;
mod bitsets;

use pyo3::prelude::*;
use std::collections::HashSet;

type Counts = (Vec<usize>, Vec<(usize, usize)>, usize);

/// Fixed-width little-endian masks, with one byte string per candidate.
/// Returns frequencies, nonempty pair (intersection, union) counts in input
/// order, and the number of distinct masks strictly contained in another.
#[pyfunction]
fn counts(masks: Vec<Vec<u8>>, universe_size: usize) -> PyResult<Counts> {
    let words = bitsets::decode_masks(&masks, universe_size)?;
    let mut frequencies = vec![0usize; universe_size];
    for mask in &words {
        for (index, &word) in mask.iter().enumerate() {
            let mut remaining = word;
            while remaining != 0 {
                frequencies[index * 64 + remaining.trailing_zeros() as usize] += 1;
                remaining &= remaining - 1;
            }
        }
    }
    let mut pairs = Vec::new();
    for (index, left) in words.iter().enumerate() {
        for right in &words[index + 1..] {
            let mut intersection = 0usize;
            let mut union = 0usize;
            for (&a, &b) in left.iter().zip(right) {
                intersection += (a & b).count_ones() as usize;
                union += (a | b).count_ones() as usize;
            }
            if union != 0 {
                pairs.push((intersection, union));
            }
        }
    }
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
    Ok((frequencies, pairs, dominated))
}

#[pymodule]
fn maxcover_structure_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(counts, module)?)?;
    module.add_function(wrap_pyfunction!(algorithms::greedy, module)?)?;
    module.add_function(wrap_pyfunction!(algorithms::lazy_greedy, module)?)?;
    Ok(())
}
