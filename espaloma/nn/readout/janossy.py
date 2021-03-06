# =============================================================================
# IMPORTS
# =============================================================================
import dgl
import torch

import espaloma as esp


# =============================================================================
# MODULE CLASSES
# =============================================================================
class JanossyPooling(torch.nn.Module):
    """ Janossy pooling (arXiv:1811.01900) to average node representation
    for higher-order nodes.


    """

    def __init__(
        self,
        config,
        in_features,
        out_features={
            1: ["sigma", "epsilon", "q"],
            2: ["k", "eq"],
            3: ["k", "eq"],
            4: ["k", "eq"],
        },
        out_features_dimensions=-1,
        pool=torch.add,
    ):
        super(JanossyPooling, self).__init__()

        # if users specify out features as lists,
        # assume dimensions to be all zero
        for level in out_features.keys():
            if isinstance(out_features[level], list):
                out_features[level] = dict(
                    zip(out_features[level], [1 for _ in out_features[level]])
                )

        # bookkeeping
        self.out_features = out_features
        self.levels = [key for key in out_features.keys() if key != 1]
        self.pool = pool

        # get output features
        mid_features = [x for x in config if isinstance(x, int)][-1]

        # set up networks
        for level in self.levels:

            # set up individual sequential networks
            setattr(
                self,
                "sequential_%s" % level,
                esp.nn.sequential._Sequential(
                    in_features=in_features * level,
                    config=config,
                    layer=torch.nn.Linear,
                ),
            )

            for feature, dimension in self.out_features[level].items():
                setattr(
                    self,
                    "f_out_%s_to_%s" % (level, feature),
                    torch.nn.Linear(mid_features, dimension,),
                )

        # atom level
        self.sequential_1 = esp.nn.sequential._Sequential(
            in_features=in_features, config=config, layer=torch.nn.Linear
        )

        for feature, dimension in self.out_features[1].items():
            setattr(
                self,
                "f_out_1_to_%s" % feature,
                torch.nn.Linear(mid_features, dimension,),
            )

    def forward(self, g):
        """ Forward pass.

        Parameters
        ----------
        g : dgl.DGLHeteroGraph,
            input graph.
        """

        # copy
        g.multi_update_all(
            {
                "n1_as_%s_in_n%s"
                % (relationship_idx, big_idx): (
                    dgl.function.copy_src("h", "m%s" % relationship_idx),
                    dgl.function.mean(
                        "m%s" % relationship_idx, "h%s" % relationship_idx
                    ),
                )
                for big_idx in self.levels
                for relationship_idx in range(big_idx)
            },
            cross_reducer="sum",
        )

        # pool
        for big_idx in self.levels:

            g.apply_nodes(
                func=lambda nodes: {
                    feature: getattr(
                        self, "f_out_%s_to_%s" % (big_idx, feature)
                    )(
                        getattr(self, "sequential_%s" % big_idx)(
                            g=None,
                            x=self.pool(
                                torch.cat(
                                    [
                                        nodes.data["h%s" % relationship_idx]
                                        for relationship_idx in range(big_idx)
                                    ],
                                    dim=1,
                                ),
                                torch.cat(
                                    [
                                        nodes.data["h%s" % relationship_idx]
                                        for relationship_idx in range(
                                            big_idx - 1, -1, -1
                                        )
                                    ],
                                    dim=1,
                                ),
                            ),
                        )
                    )
                    for feature in self.out_features[big_idx].keys()
                },
                ntype="n%s" % big_idx,
            )

        # atom level
        g.apply_nodes(
            func=lambda nodes: {
                feature: getattr(self, "f_out_1_to_%s" % feature)(
                    self.sequential_1(g=None, x=nodes.data["h"])
                )
                for feature in self.out_features[1].keys()
            },
            ntype="n1",
        )

        return g


class JanossyPoolingImproper(torch.nn.Module):
    """ Janossy pooling (arXiv:1811.01900) to average node representation
    for improper torsions.


    """

    def __init__(
        self,
        config,
        in_features,
        out_features={"k": 6,},
        out_features_dimensions=-1,
    ):
        super(JanossyPoolingImproper, self).__init__()

        # if users specify out features as lists,
        # assume dimensions to be all zero

        # bookkeeping
        self.out_features = out_features
        self.levels = ["n4_improper"]

        # get output features
        mid_features = [x for x in config if isinstance(x, int)][-1]

        # set up networks
        for level in self.levels:

            # set up individual sequential networks
            setattr(
                self,
                "sequential_%s" % level,
                esp.nn.sequential._Sequential(
                    in_features=in_features * 4,
                    config=config,
                    layer=torch.nn.Linear,
                ),
            )

            for feature, dimension in self.out_features.items():
                setattr(
                    self,
                    "f_out_%s_to_%s" % (level, feature),
                    torch.nn.Linear(mid_features, dimension,),
                )

    def forward(self, g):
        """ Forward pass.

        Parameters
        ----------
        g : dgl.DGLHeteroGraph,
            input graph.
        """

        # copy
        g.multi_update_all(
            {
                "n1_as_%s_in_%s"
                % (relationship_idx, big_idx): (
                    dgl.function.copy_src("h", "m%s" % relationship_idx),
                    dgl.function.mean(
                        "m%s" % relationship_idx, "h%s" % relationship_idx
                    ),
                )
                for big_idx in self.levels
                for relationship_idx in range(4)
            },
            cross_reducer="sum",
        )

        # pool
        #   sum over three cyclic permutations of "h0", "h2", "h3", assuming "h1" is the central atom in the improper
        #   following the smirnoff trefoil convention [(0, 1, 2, 3), (2, 1, 3, 0), (3, 1, 0, 2)]
        #   https://github.com/openforcefield/openforcefield/blob/166c9864de3455244bd80b2c24656bd7dda3ae2d/openforcefield/typing/engines/smirnoff/parameters.py#L3326-L3360
        for big_idx in self.levels:

            g.apply_nodes(
                func=lambda nodes: {
                    feature: getattr(
                        self, "f_out_%s_to_%s" % (big_idx, feature)
                    )(
                        getattr(self, "sequential_%s" % big_idx)(
                            g=None,
                            x=torch.sum(
                                torch.stack(
                                    [
                                        torch.cat(
                                            [
                                                nodes.data["h0"],
                                                nodes.data["h1"],
                                                nodes.data["h2"],
                                                nodes.data["h3"],
                                            ],
                                            dim=1,
                                        ),
                                        torch.cat(
                                            [
                                                nodes.data["h2"],
                                                nodes.data["h1"],
                                                nodes.data["h3"],
                                                nodes.data["h0"],
                                            ],
                                            dim=1,
                                        ),
                                        torch.cat(
                                            [
                                                nodes.data["h3"],
                                                nodes.data["h1"],
                                                nodes.data["h0"],
                                                nodes.data["h2"],
                                            ],
                                            dim=1,
                                        ),
                                    ],
                                    dim=0,
                                ),
                                dim=0,
                            ),
                        )
                    )
                    for feature in self.out_features.keys()
                },
                ntype=big_idx,
            )

        return g
