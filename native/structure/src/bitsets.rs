use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Validate the Python boundary once and decode arbitrary-width little-endian masks.
pub(crate) fn decode_masks(masks: &[Vec<u8>], universe_size: usize) -> PyResult<Vec<Vec<u64>>> {
    if universe_size == 0 || masks.is_empty() {
        return Err(PyValueError::new_err(
            "positive universe and nonempty candidates required",
        ));
    }
    let width = universe_size.div_ceil(8);
    let tail = universe_size % 8;
    if masks
        .iter()
        .any(|mask| mask.len() != width || (tail != 0 && mask[width - 1] >> tail != 0))
    {
        return Err(PyValueError::new_err(
            "mask width or unused high bits are invalid",
        ));
    }
    Ok(masks
        .iter()
        .map(|mask| {
            mask.chunks(8)
                .map(|chunk| {
                    let mut bytes = [0u8; 8];
                    bytes[..chunk.len()].copy_from_slice(chunk);
                    u64::from_le_bytes(bytes)
                })
                .collect()
        })
        .collect())
}

pub(crate) fn marginal(mask: &[u64], covered: &[u64]) -> usize {
    mask.iter()
        .zip(covered)
        .map(|(&word, &seen)| (word & !seen).count_ones() as usize)
        .sum()
}

pub(crate) fn cover(covered: &mut [u64], mask: &[u64]) {
    for (seen, &word) in covered.iter_mut().zip(mask) {
        *seen |= word;
    }
}
