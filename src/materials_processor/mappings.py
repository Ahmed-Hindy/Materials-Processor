"""Renderer, generic-node, and parameter mapping tables."""

###################################### CONSTANTS ######################################

STANDARDIZER_SUPPORTED_SOURCE_TYPES = ['hou_vop_nodes', 'usd_prims', 'blender_shader_nodes']

PRINCIPLED_NATIVE_NODE_TYPE = 'principledshader::2.0'
OPENPBR_NODE_TYPE = 'mtlxopen_pbr_surface'

PRINCIPLED_SHADER_PARAM_ALIASES = {
    'basecolor': 'base_color',
    'metallic': 'metalness',
    'rough': 'specular_roughness',
    'ior': 'specular_IOR',
    'reflect': 'specular',
    'coat': 'coat',
    'coatrough': 'coat_roughness',
    'transparency': 'transmission',
    'difftrans': 'transmission',
    'transcolor': 'transmission_color',
    'sss': 'subsurface',
    'subsurface': 'subsurface',
    'ssscolor': 'subsurface_color',
    'subtint': 'subsurface_color',
    'emitint': 'emission',
    'emission': 'emission',
    'emitcolor': 'emission_color',
    'opaccolor': 'opacity',
    'basecolorr': 'base_colorr',
    'basecolorg': 'base_colorg',
    'basecolorb': 'base_colorb',
    'sheen': 'sheen',
    'sheencolor': 'sheen_color',
    'coatior': 'coat_IOR',
    'coatcolor': 'coat_color',
    'surface': 'surface',
    'displacement': 'displacement',
}

PRINCIPLED_TEXTURE_INPUTS = {
    'base_color': {
        'use_parm': 'basecolor_useTexture',
        'texture_parm': 'basecolor_texture',
        'image_name': 'image_base_color',
        'signature': 'color3',
    },
    'metalness': {
        'use_parm': 'metallic_useTexture',
        'texture_parm': 'metallic_texture',
        'image_name': 'image_metalness',
        'signature': 'float',
    },
    'specular_roughness': {
        'use_parm': 'rough_useTexture',
        'texture_parm': 'rough_texture',
        'image_name': 'image_roughness',
        'signature': 'float',
    },
    'specular_IOR': {
        'use_parm': 'ior_useTexture',
        'texture_parm': 'ior_texture',
        'image_name': 'image_ior',
        'signature': 'float',
    },
    'specular': {
        'use_parm': 'reflect_useTexture',
        'texture_parm': 'reflect_texture',
        'image_name': 'image_specular',
        'signature': 'float',
    },
    'coat': {
        'use_parm': 'coat_useTexture',
        'texture_parm': 'coat_texture',
        'image_name': 'image_coat',
        'signature': 'float',
    },
    'coat_roughness': {
        'use_parm': 'coatrough_useTexture',
        'texture_parm': 'coatrough_texture',
        'image_name': 'image_coat_roughness',
        'signature': 'float',
    },
    'transmission': {
        'use_parm': 'transparency_useTexture',
        'texture_parm': 'transparency_texture',
        'image_name': 'image_transmission',
        'signature': 'float',
    },
    'transmission_color': {
        'use_parm': 'transcolor_useTexture',
        'texture_parm': 'transcolor_texture',
        'image_name': 'image_transmission_color',
        'signature': 'color3',
    },
    'subsurface': {
        'use_parm': 'sss_useTexture',
        'texture_parm': 'sss_texture',
        'image_name': 'image_subsurface',
        'signature': 'float',
    },
    'subsurface_color': {
        'use_parm': 'ssscolor_useTexture',
        'texture_parm': 'ssscolor_texture',
        'image_name': 'image_subsurface_color',
        'signature': 'color3',
    },
    'emission_color': {
        'use_parm': 'emitcolor_useTexture',
        'texture_parm': 'emitcolor_texture',
        'image_name': 'image_emission_color',
        'signature': 'color3',
    },
    'opacity': {
        'use_parm': 'opaccolor_useTexture',
        'texture_parm': 'opaccolor_texture',
        'image_name': 'image_opacity',
        'signature': 'color3',
    },
}

PRINCIPLED_NORMAL_INPUT = {
    'enable_parm': 'baseBumpAndNormal_enable',
    'type_parm': 'baseBumpAndNormal_type',
    'texture_parm': 'baseNormal_texture',
    'normalmap_name': 'normalmap_base',
    'image_name': 'image_normal',
}

PRINCIPLED_DISPLACEMENT_INPUT = {
    'enable_parm': 'dispTex_enable',
    'texture_parm': 'dispTex_texture',
    'scale_parm': 'dispTex_scale',
    'displacement_name': 'principled_displacement',
    'image_name': 'image_displacement',
}

OPENPBR_PARAM_NAMES_TO_GENERIC = {
    'base_weight': 'base',
    'base_color': 'base_color',
    'base_diffuse_roughness': 'diffuse_roughness',
    'base_metalness': 'metalness',
    'specular_weight': 'specular',
    'specular_color': 'specular_color',
    'specular_roughness': 'specular_roughness',
    'specular_ior': 'specular_IOR',
    'specular_roughness_anisotropy': 'specular_anisotropy',
    'transmission_weight': 'transmission',
    'transmission_color': 'transmission_color',
    'transmission_depth': 'transmission_depth',
    'transmission_scatter': 'transmission_scatter',
    'transmission_scatter_anisotropy': 'transmission_scatter_anisotropy',
    'transmission_dispersion_scale': 'transmission_dispersion_scale',
    'transmission_dispersion_abbe_number': 'transmission_dispersion_abbe_number',
    'subsurface_weight': 'subsurface',
    'subsurface_color': 'subsurface_color',
    'subsurface_radius': 'subsurface_radius',
    'subsurface_radius_scale': 'subsurface_radius_scale',
    'subsurface_scatter_anisotropy': 'subsurface_scatter_anisotropy',
    'fuzz_weight': 'fuzz_weight',
    'fuzz_color': 'fuzz_color',
    'fuzz_roughness': 'fuzz_roughness',
    'coat_weight': 'coat',
    'coat_color': 'coat_color',
    'coat_roughness': 'coat_roughness',
    'coat_roughness_anisotropy': 'coat_anisotropy',
    'coat_ior': 'coat_IOR',
    'coat_darkening': 'coat_darkening',
    'thin_film_weight': 'thin_film_weight',
    'thin_film_thickness': 'thin_film_thickness',
    'thin_film_ior': 'thin_film_IOR',
    'emission_luminance': 'emission',
    'emission_color': 'emission_color',
    'geometry_opacity': 'opacity',
    'geometry_thin_walled': 'thin_walled',
    'geometry_normal': 'normal',
    'geometry_coat_normal': 'coat_normal',
    'geometry_tangent': 'tangent',
    'geometry_coat_tangent': 'coat_tangent',
    'out': 'surface',
}

REDSHIFT_HOU_NODE_TYPES = {
    'redshift::StandardMaterial': 'GENERIC::standard_surface',
    'redshift::TextureSampler': 'GENERIC::image',
    'redshift::BumpMap': 'GENERIC::normalmap',
    'redshift::RSColorCorrection': 'GENERIC::color_correct',
    'redshift::RSMathRange': 'GENERIC::range',
    'redshift::RSColorRange': 'GENERIC::range',
    'redshift::Displacement': 'GENERIC::displacement',
    'redshift_material': 'GENERIC::output_node',
    'redshift_usd_material': 'GENERIC::output_node',
    'null': 'GENERIC::null',
}

REDSHIFT_USD_PRIM_TYPES = {
    'redshift::StandardMaterial': 'GENERIC::standard_surface',
    'redshift::TextureSampler': 'GENERIC::image',
    'redshift::BumpMap': 'GENERIC::normalmap',
    'redshift::Displacement': 'GENERIC::displacement',
    'redshift::RSColorCorrection': 'GENERIC::color_correct',
    'redshift::RSMathRange': 'GENERIC::range',
    'redshift::RSColorRange': 'GENERIC::range',
    'redshift_material': 'GENERIC::output_node',
    'redshift_usd_material': 'GENERIC::shader_node',
    'null': 'GENERIC::null',
}

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
            OPENPBR_NODE_TYPE: 'GENERIC::standard_surface',
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
            'ND_open_pbr_surface_surfaceshader': 'GENERIC::standard_surface',
            'ND_standard_surface_surfaceshader': 'GENERIC::standard_surface',
            'ND_image_float': 'GENERIC::image',
            'ND_image_color3': 'GENERIC::image',
            'ND_normalmap_vector3': 'GENERIC::normalmap',
            'ND_geompropvalue_vector2': 'GENERIC::uvmap',
            'ND_separate3_color3': 'GENERIC::separate_color',
            'ND_colorcorrect_color3': 'GENERIC::color_correct',
            'ND_range_float': 'GENERIC::range',
            'ND_bump_vector3': 'GENERIC::displacement',
            'ND_displacement_float': 'GENERIC::displacement',
        },
    },

    'openpbr': {
        'hou_vop_nodes': {
            OPENPBR_NODE_TYPE: 'GENERIC::standard_surface',
            'mtlximage': 'GENERIC::image',
            'mtlxnormalmap::2.0': 'GENERIC::normalmap',
            'mtlxrange': 'GENERIC::range',
            'mtlxcolorcorrect': 'GENERIC::color_correct',
            'mtlxmix': 'GENERIC::mix_rgba',
            'mtlxdisplacement': 'GENERIC::displacement',
            'subnetconnector': 'GENERIC::output_node',
            'null': 'GENERIC::null',
        },
        'usd_prims': {
            'ND_open_pbr_surface_surfaceshader': 'GENERIC::standard_surface',
            'ND_image_float': 'GENERIC::image',
            'ND_image_color3': 'GENERIC::image',
            'ND_normalmap_vector3': 'GENERIC::normalmap',
            'ND_geompropvalue_vector2': 'GENERIC::uvmap',
            'ND_separate3_color3': 'GENERIC::separate_color',
            'ND_colorcorrect_color3': 'GENERIC::color_correct',
            'ND_range_float': 'GENERIC::range',
            'ND_bump_vector3': 'GENERIC::displacement',
            'ND_displacement_float': 'GENERIC::displacement',
        },
    },

    'principledshader': {
        'hou_vop_nodes': {
            PRINCIPLED_NATIVE_NODE_TYPE: 'GENERIC::standard_surface',
            'null': 'GENERIC::null',
        },
    },

    'redshift_vopnet': {
        'hou_vop_nodes': REDSHIFT_HOU_NODE_TYPES,
    },

    'rs_usd_material_builder': {
        'hou_vop_nodes': REDSHIFT_HOU_NODE_TYPES,
        'usd_prims': REDSHIFT_USD_PRIM_TYPES,
    },

    'blender': {
        'blender_shader_nodes': {
            'ShaderNodeBsdfPrincipled': 'GENERIC::standard_surface',
            'ShaderNodeTexImage': 'GENERIC::image',
            'ShaderNodeUVMap': 'GENERIC::uvmap',
            'ShaderNodeSeparateColor': 'GENERIC::separate_color',
            'ShaderNodeNormalMap': 'GENERIC::normalmap',
            'ShaderNodeBump': 'GENERIC::displacement',
            'ShaderNodeOutputMaterial': 'GENERIC::output_node',
            'NodeReroute': 'GENERIC::null',
        },
    },

}


# 2) build *both* reverse maps automatically in one sweep
GENERIC_TO_RENDERER = {}
for renderer, profiles in REGULAR_NODE_TYPES_TO_GENERIC.items():
    GENERIC_TO_RENDERER[renderer] = {}
    for profile, mapping in profiles.items():
        GENERIC_TO_RENDERER[renderer][profile] = {
            generic: specific for specific, generic in mapping.items()
        }

# 3) a single little helper to pick which map you want:
def convert_generic(node_type: str,
                    target_renderer: str,
                    profile: str = 'hou_vop_nodes') -> str:
    """
    profile == 'hou_vop_nodes'  → VOP node‐type mapping
    profile == 'usd_prims'      → USD‐prim info:id mapping
    profile == 'blender_shader_nodes' → Blender shader node mapping
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
    OPENPBR_NODE_TYPE: OPENPBR_PARAM_NAMES_TO_GENERIC,
    'mtlximage': {
        'signature': 'signature',
        'file': 'filename',
        'texcoord': 'texcoord',
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
    'mtlxnormalmap:2.0': {
        'in': 'in',
        'scale': 'scale',
        'out': 'out',
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
    'ND_open_pbr_surface_surfaceshader': OPENPBR_PARAM_NAMES_TO_GENERIC,
    'ND_image_float': {
        'signature': 'signature',
        'file': 'filename',
        'texcoord': 'texcoord',
        'out': 'rgb',
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
        'texcoord': 'texcoord',
        'out': 'rgb',
    },
    'ND_geompropvalue_vector2': {
        'geomprop': 'uv_map',
        'default': 'default',
        'out': 'vector',
    },
    'ND_separate3_color3': {
        'in': 'rgb',
        'outr': 'r',
        'outg': 'g',
        'outb': 'b',
    },
    'ND_normalmap_vector3': {
        'in': 'in',
        'scale': 'scale',
        'out': 'out',
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
    'ND_bump_vector3': {
        'in': 'displacement',
        'scale': 'scale',
        'out': 'displacement',
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
        'bump_input': 'normal',
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
    'redshift:BumpMap': {
        'input': 'in',
        'scale': 'scale',
        'out': 'out',
    },
    'redshift:Displacement': {
        'texMap': 'displacement',
        'scale': 'scale',
        'out': 'out',
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
    'principledshader:2.0': PRINCIPLED_SHADER_PARAM_ALIASES,

    # blender parms:
    'ShaderNodeBsdfPrincipled': {
        'Weight': 'base',
        'Base Color': 'base_color',
        'Diffuse Roughness': 'diffuse_roughness',
        'Metallic': 'metalness',
        'Roughness': 'specular_roughness',
        'IOR': 'specular_IOR',
        'Alpha': 'opacity',
        'Normal': 'normal',
        'Subsurface Weight': 'subsurface',
        'Subsurface Radius': 'subsurface_radius',
        'Subsurface Scale': 'subsurface_scale',
        'Subsurface IOR': 'subsurface_IOR',
        'Subsurface Anisotropy': 'subsurface_anisotropy',
        'Specular IOR Level': 'specular',
        'Specular Tint': 'specular_color',
        'Anisotropic': 'specular_anisotropy',
        'Anisotropic Rotation': 'specular_rotation',
        'Tangent': 'tangent',
        'Transmission Weight': 'transmission',
        'Emission Color': 'emission_color',
        'Emission Strength': 'emission',
        'Coat Weight': 'coat',
        'Coat Roughness': 'coat_roughness',
        'Coat IOR': 'coat_IOR',
        'Coat Tint': 'coat_color',
        'Coat Normal': 'coat_normal',
        'Sheen Weight': 'sheen',
        'Sheen Roughness': 'sheen_roughness',
        'Sheen Tint': 'sheen_color',
        'Thin Film Thickness': 'thin_film_thickness',
        'Thin Film IOR': 'thin_film_IOR',
        'BSDF': 'surface',
    },
    'ShaderNodeTexImage': {
        'image': 'filename',
        'Vector': 'texcoord',
        'Color': 'rgb',
        'Alpha': 'alpha',
    },
    'ShaderNodeUVMap': {
        'uv_map': 'uv_map',
        'UV': 'vector',
    },
    'ShaderNodeSeparateColor': {
        'Color': 'rgb',
        'Red': 'r',
        'Green': 'g',
        'Blue': 'b',
        'Alpha': 'alpha',
    },
    'ShaderNodeNormalMap': {
        'Color': 'in',
        'Strength': 'scale',
        'Normal': 'out',
    },
    'ShaderNodeBump': {
        'Height': 'displacement',
        'Strength': 'scale',
        'Normal': 'out',
    },
}

FORMAT_CHOICES = {
    'principledshader': 'Principled Shader',
    'mtlx': 'MTLX',
    'openpbr': 'OpenPBR',
    'arnold': 'Arnold',
    'redshift_vopnet': 'Redshift VOPNET',
    'rs_usd_material_builder': 'Redshift USD Material Builder',
}
