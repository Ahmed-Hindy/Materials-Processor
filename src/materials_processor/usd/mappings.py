"""USD renderer mapping tables."""

from pxr import Sdf

# map USD material outputs back to GENERIC types
GENERIC_OUTPUT_TYPES = {
    'surface': 'GENERIC::output_surface',
    'displacement': 'GENERIC::output_displacement',
}

OUT_PRIMS_TYPES = {
    'mtlx': 'subnetconnector',
    'arnold': 'arnold_shader',
    'rs_usd_material_builder': 'redshift_usd_material',
}

SKIPPED_ATTRIBS = [
    'info:id',
    'info:implementationSource',
    'outputs:out'
]


GENERIC_NODE_TYPES_TO_REGULAR_USD = {
    'GENERIC::standard_surface': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:standard_surface',
            'mtlx': 'ND_standard_surface_surfaceshader',
            'rs_usd_material_builder': 'redshift::StandardMaterial',
            'usdpreview': 'UsdPreviewSurface',
        },
    },
    'GENERIC::image': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:image',
            'mtlx': 'ND_image_color3',
            'rs_usd_material_builder': 'redshift::TextureSampler',
            'usdpreview': 'UsdUVTexture',
        },
    },
    'GENERIC::range': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:range',
            'mtlx': 'ND_range_color3',
            'rs_usd_material_builder': 'redshift::RSColorRange',
        },
    },
    'GENERIC::color_correct': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:color_correct',
            'mtlx': 'ND_colorcorrect_color3',
            'rs_usd_material_builder': 'redshift::RSColorCorrection',
        },
    },
    'GENERIC::curvature': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:curvature',
            # 'mtlx': 'null',
            # 'rs_usd_material_builder': 'redshift::Curvature',
        },
    },
    'GENERIC::mix_rgba': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:mix_rgba',
            # 'mtlx': 'null',
        },
    },
    'GENERIC::mix_layer': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:mix_layer',
            # 'mtlx': 'null',
        },
    },
    'GENERIC::layer_rgba': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:layer_rgba',
            # 'mtlx': 'null',
        },
    },
    'GENERIC::ramp_rgb': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:ramp_rgb::2',
        },
    },
    'GENERIC::ramp_float': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:ramp_float::2',
        },
    },
    'GENERIC::displacement': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': 'arnold:bump2d',
            'mtlx':   'ND_bump_vector3',
            'rs_usd_material_builder':   'redshift::Displacement',
        },
    },
    'GENERIC::output_node': {
        'prim_type': 'Material',
        # output nodes themselves become UsdShade.Material, no info:id needed
    },
    'GENERIC::shader_node': {
        'prim_type': 'Shader',
        'info_id': {
            'rs_usd_material_builder': 'redshift_usd_material',
        },
    },
    'GENERIC::null': {
        'prim_type': 'Shader',
        'info_id': {
            'arnold': None,
            'mtlx':   None,
            'rs_usd_material_builder': None,
        },
    },
}

# for connections from material prim to stdsurface prim
OUT_PRIM_DICT = {
    'arnold': {
        'GENERIC::output_surface': {
            'src': 'shader',
            'dest': 'arnold:surface',
        },
        'GENERIC::output_displacement': {
            'src': 'displacement',
            'dest': 'arnold:displacement',
        },

    },
    'mtlx': {
        'GENERIC::output_surface': {
            'src': 'out',
            'dest': 'mtlx:surface',
        },
        'GENERIC::output_displacement': {
            'src': 'out',
            'dest': 'mtlx:displacement',
        },
    },
    'rs_usd_material_builder': {
        'GENERIC::output_surface': {
            'src': 'Shader',
            'dest': 'Redshift:surface',
        },
        'GENERIC::output_displacement': {
            'src': 'out',
            'dest': 'Redshift:displacement',
        },
    },
}





_ATTRIB_TYPE_CASTERS = {
    'int': Sdf.ValueTypeNames.Int,
    'int1': Sdf.ValueTypeNames.Int,
    'int2': Sdf.ValueTypeNames.Int2,
    'float': Sdf.ValueTypeNames.Float,
    'float1': Sdf.ValueTypeNames.Float,
    'float2': Sdf.ValueTypeNames.Float2,
    'float3': Sdf.ValueTypeNames.Float3,
    'float4': Sdf.ValueTypeNames.Float4,
    'bool': Sdf.ValueTypeNames.Bool,
    'bool1': Sdf.ValueTypeNames.Bool,
    'str': Sdf.ValueTypeNames.String,
    'str1': Sdf.ValueTypeNames.String,
    'AssetPath': Sdf.ValueTypeNames.Asset,
    'AssetPath1': Sdf.ValueTypeNames.Asset,
    'xyzw3': Sdf.ValueTypeNames.Vector3f,
    'tuple': tuple,
}
