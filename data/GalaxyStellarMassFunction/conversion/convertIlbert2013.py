from velociraptor.observations.objects import (
    ObservationalData,
    MultiRedshiftObservationalData,
)

import unyt
import numpy as np
import os
import re
import sys
import itertools as it

ORIGINAL_H = 0.7


def pairwise(iterable):
    """
    return successive pairs of elements from the iterable
    i.e. (i0, i1), (i1, i2), (i2,i3), ...

    it: the iterable to consume.
    """
    a, b = it.tee(iterable)
    next(b, None)
    return zip(a, b)


def load_file_and_split_by_z(raw_file_name):
    """
    Read the data file and do all the mucking around needed to extract a list of the
    redshift bins for which the GSMF is tabulated, along with the corresponding GSMF
    values and their errors.
    The number and spacing of the stellar mass bins vary with z; they are given in the
    first column of the returned array.

    raw_file_name: the file name of the raw data file to extract the GSMF from
    """
    with open(raw_file_name, "r") as f:
        lines = f.readlines()

    # find header lines indicating the start of each block of data
    header_line_nos = [i for i, line in enumerate(lines) if ".dat" in line]
    header_line_nos.append(len(lines))

    # split the full list of lines into one block of lines per redshift bin
    split_lines = []
    for l1, l2 in pairwise(header_line_nos):
        split_lines.append(lines[l1:l2])

    # figure out the redshift bins
    z_bins_arr = np.zeros((len(split_lines), 2))
    gsmf_arr = []
    for isl, lines in enumerate(split_lines):
        z_bins_arr[isl] = list(
            map(float, re.search("z_(\d.\d)_(\d.\d)", lines[0]).groups())
        )
        gsmf_arr.append(np.loadtxt(lines, usecols=range(4)))

    return z_bins_arr, gsmf_arr


def process_for_redshift(z, gsmf_and_Mstar_at_z):
    """
    Output an HDF5 file containing the GSMF at a given redshift.

    z: the redshift to produce the GSMF for. The given value corresponds to the lower
    edge of a range in redshift of width 0.5, except for the first bin 0.2 < z < 0.5,
    and the last bin 3.0 < z < 4.0
    gsmf_and_mstar_at_z: the array containing stellar mass bins and the GSMF at the
    chosen redshift
    """

    processed = ObservationalData()

    plot_as = "points"
    h = cosmology.h

    Mstar_bins = gsmf_and_Mstar_at_z[:, 0]
    M = 10 ** Mstar_bins * (h / ORIGINAL_H) ** (-2) * unyt.Solar_Mass
    Phi = 10 ** gsmf_and_Mstar_at_z[:, 1] * (h / ORIGINAL_H) ** 3 * unyt.Mpc ** (-3)
    # y_scatter should be a 1xN or 2xN array describing offsets from
    # the median point 'y'
    # Errors are log error dz = 1/ln(10) dy/y
    # We want dy = y ln(10) dz
    Phi_err = (
        (
            10 ** gsmf_and_Mstar_at_z[:, 1][:, None]
            * np.log(10)
            * gsmf_and_Mstar_at_z[:, 2:]
        ).T
        * (h / ORIGINAL_H) ** 3
        * unyt.Mpc ** (-3)
    )

    processed.associate_x(
        M, scatter=None, comoving=True, description="Galaxy Stellar Mass"
    )
    processed.associate_y(Phi, scatter=Phi_err, comoving=True, description="Phi (GSMF)")
    processed.associate_redshift(sum(z) * 0.5, *z)
    processed.associate_plot_as(plot_as)

    return processed


# Exec the master cosmology file passed as first argument
# These lines are _required_ and you are required to use
# the cosmology specified (this is an astropy.cosmology
# instance)
with open(sys.argv[1], "r") as handle:
    exec(handle.read())

input_filename = "../raw/Ilbert2013.txt"

output_filename = "Ilbert2013.hdf5"
output_directory = "../"

if not os.path.exists(output_directory):
    os.mkdir(output_directory)
comment = (
    "Assuming Chabrier IMF and Vmax selection, quoted redshift is lower bound of range. "
    f"h-corrected for SWIFT using Cosmology: {cosmology.name}."
)
citation = "Ilbert et al. (2013)"
bibcode = "2013A&A...556A..55I"
name = "GSMF from UltraVISTA"

multi_z = MultiRedshiftObservationalData()
multi_z.associate_comment(comment)
multi_z.associate_name(name)
multi_z.associate_citation(citation, bibcode)
multi_z.associate_cosmology(cosmology)

# z_bins is a 1-D ndarray containing the lower edges of the redshift bins
# gsmf_and_Mstar is a list of 2D ndarrays, one per redshift
# Each contains five columns as follows:
# log(Mstar) bins, Mstar errors, log(GSMF), GSMF +- errors
z_bins, gsmf_and_Mstar = load_file_and_split_by_z(input_filename)

for z, gsmf_and_Mstar_at_z in zip(z_bins, gsmf_and_Mstar):
    multi_z.associate_dataset(process_for_redshift(z, gsmf_and_Mstar_at_z))

output_path = f"{output_directory}/{output_filename}"

if os.path.exists(output_path):
    os.remove(output_path)

multi_z.write(filename=output_path)
