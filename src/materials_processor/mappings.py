"""Renderer, generic-node, and parameter mapping tables."""

###################################### CONSTANTS ######################################

STANDARDIZER_SUPPORTED_SOURCE_TYPES = ['hou_vop_nodes', 'usd_prims']

REGULAR_NODE_TYPES_TO_GENERIC = {
    'arnold': {
        'hou_vop_nodes': {
            'arnold::standard_surface': 'GENERIC::standard_surface',
            'arnold::image': 'GENERIC::image',
            'arnold::normal_map': 'GENERIC::normalmap',
            'arnold::range': 'GENERIC::range',
            'arnold::color_correct': 'GENERIC::color_correct',
            'arnold::curvature': 'GENERIC::curvature',
            'arnold::mix_rgba': 'GENERIC::mix_rgba',
            'arnold::mix_layer': 'GENERIC::mix_layer',
            'arnold::layer_rgba': 'GENERIC::layer_rgba',
            'arnold::ramp_rgb::2': 'GENERIC::ramp_rgb',
            'arnold::ramp_float::2': 'GENERIC::ramp_float',
            'arnold_material': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
        'usd_prims': {
            'arnold:standard_surface': 'GENERIC::standard_surface',
            'arnold:image': 'GENERIC::image',
            'arnold:range': 'GENERIC::range',
            'arnold:color_correct': 'GENERIC::color_correct',
            'arnold:curvature': 'GENERIC::curvature',
            'arnold:mix_rgba': 'GENERIC::mix_rgba',
            'arnold:mix_layer': 'GENERIC::mix_layer',
            'arnold:layer_rgba': 'GENERIC::layer_rgba',
            'arnold:ramp_rgb::2': 'GENERIC::ramp_rgb',
            'arnold:ramp_float::2': 'GENERIC::ramp_float',
            'arnold_material': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
    },

    'mtlx': {
        'hou_vop_nodes': {
            'mtlxstandard_surface': 'GENERIC::standard_surface',
            'mtlximage': 'GENERIC::image',
            'mtlxnormalmap::2.0': 'GENERIC::normalmap',
            'mtlxrange': 'GENERIC::range',
            'mtlxcolorcorrect': 'GENERIC::color_correct',
            'mtlxmix': 'GENERIC::mix_rgba',  # it can be mix layer or mix RGBA, need specific methods to handle those niche cases.
            'mtlxdisplacement': 'GENERIC::displacement',
            'subnetconnector': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
        'usd_prims': {
            # mtlx usd prims infoId:
            'ND_standard_surface_surfaceshader': 'GENERIC::standard_surface',
            'ND_image_float': 'GENERIC::image',
            'ND_image_color3': 'GENERIC::image',
            'ND_colorcorrect_color3': 'GENERIC::color_correct',
            'ND_range_float': 'GENERIC::range',
            'ND_displacement_float': 'GENERIC::displacement',
        },
    },

    'principledshader': {
        'hou_vop_nodes': {
            'mtlxstandard_surface': 'GENERIC::standard_surface',
            'mtlximage': 'GENERIC::image',
            'mtlxnormalmap::2.0': 'GENERIC::normalmap',
            'mtlxrange': 'GENERIC::range',
            'mtlxcolorcorrect': 'GENERIC::color_correct',
            'mtlxmix': 'GENERIC::mix_rgba',
            # it can be mix layer or mix RGBA, need specific methods to handle those niche cases.
            'mtlxdisplacement': 'GENERIC::displacement',
            'subnetconnector': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
    },

    'rs_usd_material_builder': {
        'hou_vop_nodes': {
            'redshift::StandardMaterial': 'GENERIC::standard_surface',
            'redshift::TextureSampler': 'GENERIC::image',
            'redshift::Displacement': 'GENERIC::displacement',
            'redshift_material': 'GENERIC::output_node',
            'redshift_usd_material': 'GENERIC::shader_node',
            'null': 'GENERIC::null',
        },
        'usd_prims': {
            'redshift::StandardMaterial': 'GENERIC::standard_surface',
            'redshift::TextureSampler': 'GENERIC::image',
            'redshift::Displacement': 'GENERIC::displacement',
            'redshift_material': 'GENERIC::output_node',
            'redshift_usd_material': 'GENERIC::shader_node',
            'null': 'GENERIC::null',
        },
    },

}


# 2) build *both* reverse maps automatically in one sweep
GENERIC_TO_RENDERER = {}
for renderer, profiles in REGULAR_NODE_TYPES_TO_GENERIC.items():
    GENERIC_TO_RENDERER[renderer] = {
        'hou_vop_nodes': {generic: specific
                          for specific, generic in profiles.get('hou_vop_nodes', {}).items()},
        'usd_prims':   {generic: specific
                        for specific, generic in profiles.get('usd_prims', {}).items()},
    }

# 3) a single little helper to pick which map you want:
def convert_generic(node_type: str,
                    target_renderer: str,
                    profile: str = 'hou_vop_nodes') -> str:
    """
    profile == 'hou_vop_nodes'  → VOP node‐type mapping
    profile == 'usd_prims'      → USD‐prim info:id mapping
    """
    lookup = GENERIC_TO_RENDERER[target_renderer].get(profile, {})
    return lookup.get(node_type,
           lookup.get('GENERIC::null'))


"""
standardization dict for parameters. {<orig_parm_name>: <generic_name>}. Any other node type will be filtered out.
"""
REGULAR_PARAM_NAMES_TO_GENERIC = {
    # mtlx parms
    'mtlxstandard_surface': {
        'base': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_color': 'specular_color',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'specular_anisotropy': 'specular_anisotropy',
        'specular_rotation': 'specular_rotation',
        'coat': 'coat',
        'coat_color':  'coat_color',
        'coat_roughness': 'coat_roughness',
        'transmission': 'transmission',
        'transmission_color': 'transmission_color',
        'transmission_extra_roughness': 'transmission_extra_roughness',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_color': 'emission_color',
        'opacity': 'opacity',
        'normal': 'normal',
        'thin_walled': 'thin_walled',
        'out': 'surface',
    },
    'mtlximage': {
        'signature': 'signature',
        'file': 'filename',
        'out': 'rgb',
    },
    'mtlxcolorcorrect': {
        'hue': 'hue',
        'saturation': 'saturation',
        'gamma': 'gamma',
        'lift': 'lift',
        'gain': 'gain',
        'contrast': 'contrast',
        'contrastpivot': 'contrastpivot',
        'exposure': 'exposure',
        'out': 'rgb',
    },
    'mtlxrange': {
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outlow': 'outlow',
        'outhigh': 'outhigh',
        'out': 'rgb',
    },
    'mtlxmix': {
        'signature': 'signature',
        'fg_color3r': 'fg_color3r',
        'fg_color3g': 'fg_color3g',
        'fg_color3b': 'fg_color3b',
        'bg_color3r': 'bg_color3r',
        'bg_color3g': 'bg_color3g',
        'bg_color3b': 'bg_color3b',
        'mix': 'mix',
        'out': 'rgb',
    },
    'mtlxdisplacement': {
        'displacement': 'displacement',
        'scale': 'scale',
        'out': 'displacement',
    },

    # mtlx prims infoId:
    'ND_standard_surface_surfaceshader': {
        'base': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_color': 'specular_color',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'specular_anisotropy': 'specular_anisotropy',
        'specular_rotation': 'specular_rotation',
        'coat': 'coat',
        'coat_color': 'coat_color',
        'coat_roughness': 'coat_roughness',
        'transmission': 'transmission',
        'transmission_color': 'transmission_color',
        'transmission_extra_roughness': 'transmission_extra_roughness',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_color': 'emission_color',
        'opacity': 'opacity',
        'normal': 'normal',
        'thin_walled': 'thin_walled',
    },
    'ND_image_float': {
        'signature': 'signature',
        'file': 'filename',
    },
    'ND_range_float': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
    },
    'ND_range_color3': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
    },
    'ND_image_color3': {
        'signature': 'signature',
        'file': 'filename',
    },
    'ND_colorcorrect_color3': {
        'contrast': 'contrast',
        'contrastpivot': 'contrastpivot',
        'exposure': 'exposure',
        'gain': 'gain',
        'gamma': 'gamma',
        'hue': 'hue',
        'in': 'in',
        'lift': 'lift',
        'saturation': 'saturation',
    },
    'ND_displacement_float': {
        'displacement': 'displacement',
        'scale': 'scale',
    },



    # redshiftvopnet parms:
    'redshift:StandardMaterial': {
        'base_color_weight': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'refl_weight': 'specular',
        'refl_color': 'specular_color',
        'refl_roughness': 'specular_roughness',
        'refl_ior': 'specular_IOR',
        'refl_aniso': 'specular_anisotropy',
        'refl_aniso_rotation': 'specular_rotation',
        'coat_weight': 'coat',
        'coat_color': 'coat_color',
        'coat_roughness': 'coat_roughness',
        'refr_weight': 'transmission',
        'refr_color': 'transmission_color',
        'refr_roughness': 'transmission_extra_roughness',
        'ms_amount': 'subsurface',
        'ms_color': 'subsurface_color',
        'emission_weight': 'emission',
        'emission_color': 'emission_color',
        'opacity_color': 'opacity',
        # 'normal': 'normal',  # unsupported
        'refr_thin_walled': 'thin_walled',
        'outColor': 'shader',
    },
    'redshift:TextureSampler': {
        'tex0': 'filename',
        'outColor': 'rgb',
    },
    'redshift:RSMathRange': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
        'outColor': 'rgb',
    },
    'redshift:RSColorRange': {
        'in': 'in',
        'inlow': 'inlow',
        'inhigh': 'inhigh',
        'gamma': 'gamma',
        'outhigh': 'outhigh',
        'outlow': 'outlow',
        'outColor': 'rgb',
    },
    'redshift:RSColorCorrection': {
        'contrast': 'contrast',
        'contrastpivot': 'contrastpivot',
        'exposure': 'exposure',
        'gain': 'gain',
        'gamma': 'gamma',
        'hue': 'hue',
        'in': 'in',
        'lift': 'lift',
        'saturation': 'saturation',
        'outColor': 'rgb',
    },
    'redshift:Displacement': {
        'texMap': 'filename',
        'scale': 'scale',
        'outColor': 'rgb',
    },



    # arnold parms:
    'arnold:standard_surface': {
        'base': 'base',
        'base_color': 'base_color',
        'diffuse_roughness': 'diffuse_roughness',
        'metalness': 'metalness',
        'specular': 'specular',
        'specular_color': 'specular_color',
        'specular_roughness': 'specular_roughness',
        'specular_IOR': 'specular_IOR',
        'specular_anisotropy': 'specular_anisotropy',
        'specular_rotation': 'specular_rotation',
        'transmission': 'transmission',
        'transmission_color': 'transmission_color',
        'transmission_extra_roughness': 'transmission_extra_roughness',
        'coat': 'coat',
        'coat_color': 'coat_color',
        'coat_roughness': 'coat_roughness',
        'subsurface': 'subsurface',
        'subsurface_color': 'subsurface_color',
        'emission': 'emission',
        'emission_color': 'emission_color',
        'opacity': 'opacity',
        'shader': 'shader',
    },
    'arnold:image': {
        'filename': 'filename',
        'rgba': 'rgba',
    },
    'arnold:color_correct': {
        'gamma': 'gamma',
        'hue_shift': 'hue',
        'saturation': 'saturation',
        'contrast': 'contrast',
        'contrast_pivot': 'contrastpivot',
        'exposure': 'exposure',
        'multiply': 'multiply',
        'add': 'add',
        'rgba': 'rgba',
    },
    'arnold:range': {
        'input_min': 'inlow',
        'input_max': 'inhigh',
        'output_min': 'outlow',
        'output_max': 'outhigh',
        'contrast': 'contrast',
        'contrast_pivot': 'contrastpivot',
        'bias': 'bias',
        'gain': 'gain',
        'rgb': 'rgb',
    },
    'arnold:mix_rgba': {
        'input1r': 'fg_color3r',
        'input1g': 'fg_color3g',
        'input1b': 'fg_color3b',
        'input2r': 'bg_color3r',
        'input2g': 'bg_color3g',
        'input2b': 'bg_color3b',
        'mix': 'mix',
        'rgba': 'rgba',
    },
    'arnold:curvature': {
        'radius': 'radius',
        'spread': 'spread',
        'threshold': 'threshold',
        'bias': 'bias',
        'rgb': 'rgb',
    },




    # principled shader 2.0:
    'principledshader:2.0': {
        'basecolor': 'base_color',
        'metallic': 'metalness',
        'rough': 'specular_roughness',
        'ior': 'specular_IOR',
        'reflect': 'specular',
        'difftrans': 'transmission',
        'emission': 'emission',
        'opaccolor': 'opacity',
        'subsurface': 'subsurface',
        'subtint': 'subsurface_color',
        'basecolorr': 'base_colorr',
        'basecolorg': 'base_colorg',
        'basecolorb': 'base_colorb',
        'sheen': 'sheen',
        'sheencolor': 'sheen_color',
        'coat': 'coat',
        'coatrough': 'coat_roughness',
        'coatior': 'coat_IOR',
        'coatcolor': 'coat_color',
    }
}

FORMAT_CHOICES = {
    'principledshader': 'Principled Shader',
    'mtlx': 'MTLX',
    'arnold': 'Arnold',
    'rs_usd_material_builder': 'Redshift USD Material Builder',
}
