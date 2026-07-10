def test_import():
    import caereflex
    from caereflex.version import __version__

    assert caereflex.__version__ == __version__
