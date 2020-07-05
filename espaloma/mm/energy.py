# =============================================================================
# IMPORTS
# =============================================================================
import dgl
import espaloma as esp

# =============================================================================
# ENERGY IN HYPERNODES
# =============================================================================
def apply_bond(nodes):
    """ Bond energy in nodes. """
    return {
        'u': esp.mm.bond.harmonic_bond(
            x=nodes.data['x'],
            k=nodes.data['k'],
            eq=nodes.data['eq'],
        )
    }

def apply_angle(nodes):
    """ Angle energy in nodes. """
    return {
        'u': esp.mm.angle.harmonic_angle(
            x=nodes.data['x'],
            k=nodes.data['k'],
            eq=nodes.data['eq'],
        )
    }

def apply_torsion(nodes):
    """ Torsion energy in nodes. """
    return {
        'u': esp.mm.torsion.periodic_torsion(
            x=nodes.data['x'],
            k=nodes.data['k'],
            eq=nodes.data['eq'],
        )
    }

# =============================================================================
# ENERGY IN GRAPH
# =============================================================================
def energy_in_graph(g):
    """ Calculate the energy of a small molecule given parameters and geometry.

    Parameters
    ----------
    g : `dgl.DGLHeteroGraph`
        Input graph.

    Returns
    -------
    g : `dgl.DGLHeteroGraph`
        Output graph.

    Notes
    -----
    This function modifies graphs in-place.

    """

    # apply energy function
    g.apply_nodes(apply_bond, ntype='n2')
    g.apply_nodes(apply_angle, ntype='n3')
    # g.apply_nodes(apply_torsion, ntype='n4')

    # sum up energy
    g.multi_update_all(
        {
            'n%s_in_g' % idx: (
                dgl.function.copy_src(src='u', out='m%s' % idx),
                dgl.function.sum(msg='m%s' % idx, out='u%s' % idx)
            ) for idx in [2, 3]
        },
        'sum'
    )

    g.apply_nodes(
        lambda node: {
            'u': node.data['u2'] + node.data['u3']
        },
        ntype='g'
    )

    return g
