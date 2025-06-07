import hou
import os

texture_path = r"F:\Assets 3D\Models\Props\Flamethrower\textures/"
# print(texture_path)

materials = hou.selectedNodes()[0]
materials_name = materials.name()

### get all shaders
shaders = materials.children()

ArnoldShaders = materials.parent().createNode("matnet", "materials")
ArnoldShaders.moveToGoodPosition()

for shd in shaders:
    shd_type = shd.type().name()
    # print(shd_type)
    if shd_type == "principledshader::2.0":
        ArnoldVopNet = ArnoldShaders.createNode("arnold_materialbuilder",
                                                shd.name())
        ArnoldMatOutput = ArnoldVopNet.children()[0]  # "OUT_material" VOPnode

        ArnoldMat = ArnoldVopNet.createNode("arnold::standard_surface")

        ### connect nodes
        ArnoldMatOutput.setInput(0, ArnoldMat)

        ### get the textures
        basecolor = shd.evalParm("basecolor_texture")
        roughness = shd.evalParm("rough_texture")
        metallic = shd.evalParm("metallic_texture")
        normal = shd.evalParm("baseNormal_texture")

        ### set parameters
        ArnoldMat.parm("specular").set(0)
        ArnoldMat.parm("specular_roughness").set(1)

        if (basecolor != ""):
            basecolor_name = (os.path.split(basecolor)[-1])
            # print(texture_name)

            ### create basecolor texture node
            ArnoldTexBaseColor = ArnoldVopNet.createNode("arnold::image", "basecolor")
            ArnoldTexBaseColor.parm("filename").set(texture_path + basecolor_name)
            ArnoldMat.setInput(1, ArnoldTexBaseColor)

        if (roughness != ""):
            roughness_name = (os.path.split(roughness)[-1])

            ### create roughness texture node
            ArnoldTexRough = ArnoldVopNet.createNode("arnold::image", "roughness")
            ArnoldTexRough.parm("filename").set(texture_path + roughness_name)
            ArnoldMat.setInput(6, ArnoldTexRough)

        if (metallic != ""):
            metallic_name = (os.path.split(metallic)[-1])

            ### create metallic texture node
            ArnoldTexMetal = ArnoldVopNet.createNode("arnold::image", "metallic")
            ArnoldTexMetal.parm("filename").set(texture_path + metallic_name)
            ArnoldMat.setInput(3, ArnoldTexMetal)

        if (normal != ""):
            normal_name = (os.path.split(normal)[-1])

            ### create normal texture node
            ArnoldTexNormal = ArnoldVopNet.createNode("arnold::image", "normal")
            ArnoldTexNormal.parm("filename").set(texture_path + normal_name)
            ArnoldNormalMap = ArnoldVopNet.createNode("arnold::normal_map")
            ArnoldNormalMap.parm("color_to_signed").set(0)
            ArnoldNormalMap.setInput(0, ArnoldTexNormal)
            ArnoldMat.setInput(39, ArnoldNormalMap)


        #
        ArnoldShaders.layoutChildren()
        ArnoldVopNet.layoutChildren()

# Add code to modify contained geometries.
# Use drop down menu to select esxamples.


# p1 = r"$HIP/folder1/folder2/baseColor.jpeg"
# p2 = r"$HIP\folder1\folder2\baseColor.jpeg"
# 
# print(os.path.split(p1)[-1])
# print(os.path.split(p2)[-1])

