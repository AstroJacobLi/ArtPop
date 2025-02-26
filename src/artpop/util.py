# Standard library
import os
import tarfile

# Third-party
import requests
import numpy as np
from astropy import units as u
from astropy.utils.misc import isiterable

# Project
from . import MIST_PATH
from .log import logger
from .filters import phot_system_list


__all__ = ['check_random_state',
           'check_units',
           'check_odd',
           'check_xy_dim',
           'embed_slices',
           'fetch_mist_grid_if_needed']


def check_random_state(seed):
    """
    Turn seed into a `~numpy.random.RandomState` instance.

    Parameters
    ----------
    seed : `None`, int, list of ints, or `~numpy.random.RandomState`
        If ``seed`` is `None`, return the `~numpy.random.RandomState`
        singleton used by ``numpy.random``.  If ``seed`` is an `int`,
        return a new `~numpy.random.RandomState` instance seeded with
        ``seed``.  If ``seed`` is already a `~numpy.random.RandomState`,
        return it.  Otherwise raise ``ValueError``.

    Returns
    -------
    random_state : `~numpy.random.RandomState`
        RandomState object.

    Notes
    -----
    This routine is adapted from scikit-learn. See
    http://scikit-learn.org/stable/developers/utilities.html#validation-tools.
    """
    import numbers

    if seed is None or seed is np.random:
        return np.random.mtrand._rand
    if isinstance(seed, (numbers.Integral, np.integer)):
        return np.random.RandomState(seed)
    if isinstance(seed, np.random.RandomState):
        return seed
    if type(seed) == list:
        if type(seed[0]) == int:
            return np.random.RandomState(seed)

    raise ValueError('{0!r} cannot be used to seed a numpy.random.RandomState'
                     ' instance'.format(seed))


def check_units(value, default_unit):
    """
    Check if an object has units. If not, apply the default unit.

    Parameters
    ----------
    value : float, list-like, or `~astropy.units.Quantity`
        Parameter that has units.
    default_unit : str or `astropy` unit
        The default unit to apply to `value` if it does not have units.

    Returns
    -------
    quantity : `~astropy.units.Quantity`
        `value` with ``astropy`` units.
    """
    t = type(default_unit)
    if type(value) == u.Quantity:
        quantity = value
    elif (t == u.IrreducibleUnit) or (t == u.Unit) or (t == u.CompositeUnit):
        quantity = value * default_unit
    elif t == str:
        quantity = value * getattr(u, default_unit)
    else:
        raise Exception('default_unit must be an astropy unit or string')
    return quantity


def check_odd(val, name='value'):
    """
    Raise Exception if  `val` is not odd.
    """
    if isiterable(val):
        if np.any(np.asarray(val) % 2 == 0):
            raise Exception(f'{name} must be odd')
    else:
        if val % 2 == 0:
            raise Exception(f'{name} must be odd')


def check_xy_dim(xy_dim, force_odd=True):
    """
    Check the format of `xy_dim`.

    Parameters
    ----------
    xy_dim : int or list-like
        The dimensions of mock image in xy units. If `int` is given, it is
        assumed to be both the x and y dimensions and (xy_dim, xy_dim) will be
        returned. Otherwise xy_dim will be returned.
    force_odd : bool, optional
        If True (default), force both the x and y dimensions to be odd.

    Returns
    -------
    xy_dim : `~numpy.ndarray`
        Dimensions of mock image in xy units.
    """
    if not isiterable(xy_dim):
        xy_dim = [xy_dim, xy_dim]
    xy_dim = np.asarray(xy_dim).astype(int)
    if force_odd:
        check_odd(xy_dim, 'xy dimensions')
    return xy_dim


def embed_slices(center, model_shape, image_shape):
    """
    Get slices to embed smaller model array into larger image array.

    Parameters
    ----------
    center : `~numpy.ndarray`
        Center of array in the image coordinates.
    model_shape : tuple
        Shape of the array to embed (dimensions must be odd).
    image_shape : tuple
        Shape of the main image array.

    Returns
    -------
    img_slice, mod_slice : tuples of slices
        Slicing indices. To embed array in image,
        use the following: image[img_slice] = model[mod_slice]
    """
    model_shape = np.asarray(model_shape)
    image_shape = np.asarray(image_shape)

    check_odd(model_shape, 'embed_slices array shape')

    imin = center - model_shape // 2
    imax = center + model_shape // 2

    amin = (imin < np.array([0, 0])) * (-imin)
    amax = model_shape * (imax <= image_shape - 1) +\
        (model_shape - (imax - image_shape + 1)) * (imax > image_shape - 1)

    imin = np.maximum(imin, np.array([0, 0]))
    imax = np.minimum(imax, np.array(image_shape) - 1)
    imax += 1

    img_slice = np.s_[imin[0]:imax[0], imin[1]:imax[1]]
    mod_slice = np.s_[amin[0]:amax[0], amin[1]:amax[1]]

    return img_slice, mod_slice


def fetch_mist_grid_if_needed(phot_system, v_over_vcrit=0.4,
                              mist_path=MIST_PATH, overwrite=False):
    """
    If needed, fetch MIST grid from http://waps.cfa.harvard.edu/MIST.

    Parameters
    ----------
    phot_system : str
        Photometric system grid to fetch. Must be a supported ArtPop filter
        system, where are listed in `~artpop.filters.phot_system_list`.
    v_over_vcrit : float, optional
        Rotation rate divided by the critical surface linear velocity. Current
        options are 0.4 (default) and 0.0.
    mist_path : str, optional
        Path to MIST isochrone grids. Use this if you want to use a different
        path from the default location of ~/.artpop/mist (or the `MIST_PATH`
        environment variable if you have it set).
    overwrite : bool, optional
        If True, force an overwrite of grid if it exists.
     """
    if phot_system not in phot_system_list:
        raise Exception(f'Photometric system must be in {phot_system_list}.')
    version = 1.2
    url = f'http://waps.cfa.harvard.edu/MIST/data/tarballs_v{version}'
    url += f'/MIST_v{version}_vvcrit{v_over_vcrit}_{phot_system}.txz'
    tarball = os.path.join(mist_path, os.path.basename(url))
    grid_path = tarball.replace('.txz', '')
    if overwrite or not os.path.isdir(grid_path):
        logger.info(
            f'Fetching MIST synthetic photometry grid for {phot_system}.')
        r = requests.get(url, stream=True)
        with open(tarball, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        logger.info(f'Extracting grid from {os.path.basename(url)}.')
        with tarfile.open(tarball) as tar:
            tar.extractall(mist_path)
        os.remove(tarball)

    # Also download the basic isochrone grid
    url = f'http://waps.cfa.harvard.edu/MIST/data/tarballs_v{version}'
    url += f'/MIST_v{version}_vvcrit{v_over_vcrit}_basic_isos.txz'
    tarball = os.path.join(mist_path, os.path.basename(url))
    grid_path = tarball.replace('.txz', '')
    if overwrite or not os.path.isdir(grid_path):
        logger.info(
            f'Fetching MIST basic isochrone grid.')
        r = requests.get(url, stream=True)
        with open(tarball, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        logger.info(f'Extracting grid from {os.path.basename(url)}.')
        with tarfile.open(tarball) as tar:
            tar.extractall(mist_path)
        os.remove(tarball)


def trim_mist_grid_if_needed(v_over_vcrit=0.4, mist_path=MIST_PATH, overwrite=False):
    """
    If needed, trim MIST isochrones to have a better format for interpolation.
    Only relavent columns are kept.

    Parameters
    ----------
    v_over_vcrit : float, optional
        Rotation rate divided by the critical surface linear velocity. Current
        options are 0.4 (default) and 0.0.
    mist_path : str, optional
        Path to MIST isochrone grids. Use this if you want to use a different
        path from the default location of ~/.artpop/mist (or the `MIST_PATH`
        environment variable if you have it set).
    overwrite : bool, optional
        If True, force an overwrite of grid if it exists.
    """
    from .stars._read_mist_models import IsoReader

    log_ages = []
    fehs = []
    all_isos = []

    print('Trimming MIST isochrones...')
    for feh in [-4.0, -3.5, -3.0, -2.5, -2, -1.75, -1.5,
                -1.25, -1.0, -0.75, -0.50, -0.25, 0, 0.25, 0.5]:
        v = f'{v_over_vcrit:.1f}'
        ver = 'v1.2'
        sign = 'm' if feh < 0 else 'p'
        fn = f'MIST_{ver}_feh_{sign}{abs(feh):.2f}_afe_p0.0_vvcrit{v}_basic.iso'
        path = os.path.join(mist_path, 'MIST_' + ver +
                            f'_vvcrit{v}_basic_isos')
        fn = os.path.join(path, fn)
        iso_cmd = IsoReader(fn, verbose=False)

        for age in np.arange(5, 10.35, 0.05):
            all_isos.append(
                np.array(iso_cmd.isos[iso_cmd.age_index(age)].tolist()))
            log_ages.append(age)
            fehs.append(feh)

        if feh == 0.5:
            datatype = iso_cmd.isos[iso_cmd.age_index(age)].dtype

        del iso_cmd

    log_ages = np.array(log_ages)
    fehs = np.array(fehs)

    output_path = os.path.join(
        mist_path, f'MIST_{ver}_vvcrit{v}_basic_trimmed')
    if not os.path.isdir(output_path):
        os.mkdir(output_path)
    if overwrite or not os.path.isfile(os.path.join(output_path, 'isos.npy')):
        logger.info(
            f'Trimming MIST basic isochrone grid.')
        np.save(os.path.join(output_path, 'log_ages_fehs.npy'),
                np.vstack([log_ages, fehs]))
        np.save(os.path.join(output_path, 'isos.npy'), all_isos)
        np.save(os.path.join(output_path, 'datatype.npy'), datatype)
        print('Done trimming MIST isochrones and saved to files.')


def mag_to_image_amplitude(m_tot, r_sky, n, ellip, zpt, pixel_scale):
    """
    Convert total magnitude into amplitude parameter for the smooth Sersic model.

    Parameters
    ----------
    m_tot : float
        Total magnitude in the smooth component of the system.
    zpt : float
        Photometric zero point.

    Returns
    -------
    mu_e : float
        Surface brightness at the effective radius of the Sersic
        distribution in mags per square arcsec.
    amplitude : float
        Amplitude parameter for the smooth model in image flux units.
    param_name : str
        Name of amplitude parameter (needed to set its value when
        generating the smooth model).
    """
    from scipy.special import gammaincinv, gamma
    param_name = 'amplitude'
    b_n = gammaincinv(2.0 * n, 0.5)
    f_n = gamma(2 * n) *n * np.exp(b_n) / b_n**(2 * n)
    r_circ = r_sky * np.sqrt(1 - ellip)
    area = np.pi * r_circ.to('arcsec').value**2
    mu_e = m_tot + 2.5 * np.log10(2 * area) + 2.5 * np.log10(f_n)
    amplitude = 10**(0.4 * (zpt - mu_e)) * pixel_scale.value**2
    return mu_e, amplitude, param_name