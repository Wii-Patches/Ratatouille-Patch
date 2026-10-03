"""The retail releases of Disney-Pixar Ratatouille (Wii).

Six discs, five distinct main.dol files: the Scandinavian and Italian/Greek discs
carry the same one.  `dol_md5` is the retail main.dol, used to refuse modified dumps.
"""
REGIONS = {
    'RLWE78': dict(label='Ratatouille (USA)', short='USA', version=0,
                   dol_md5='b80882a32d03eb92add5d13d58bab5ec'),
    'RLWP78': dict(label='Ratatouille (UK, Australia)', short='UK/Australia', version=0,
                   dol_md5='c54d2e1a139c49f1cbd2b29987bfaf5b'),
    'RLWW78': dict(label='Ratatouille (Scandinavia)', short='Scandinavia', version=0,
                   dol_md5='3fb1fb40412a45b1e11128581df9f36f'),
    'RLWX78': dict(label='Ratatouille (Europe: Fr, De, Nl)', short='Europe FR/DE/NL', version=0,
                   dol_md5='6bdc75dc34c9b0e24b2e6d7ceabe9eba'),
    'RLWY78': dict(label='Ratatouille (Europe: It, El)', short='Europe IT/EL', version=0,
                   dol_md5='3fb1fb40412a45b1e11128581df9f36f'),
    'RLWZ78': dict(label='Ratatouille (Europe: Es, Pt)', short='Europe ES/PT', version=0,
                   dol_md5='89e7e336d76cdb85d031dc6a92996037'),
}
