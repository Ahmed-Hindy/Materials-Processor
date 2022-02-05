import hou
import os
import toolutils


class MaterialsCreator:
    def __init__(self):
        # Extras to be defined:
        self.texture_path = ""
        # print(f"printing orig texture path... >{self.texture_path}")

    def MatNet_to_use(self):
        current_tab = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor, 0)
        current_tab_parent = current_tab.pwd()
        # print(f"current_tab_parent.type().name() is {current_tab_parent.type().name()}")

        if current_tab_parent.type().name() != "matnet":
            try:
                if hou.selectedNodes()[0].type().name() != "matnet":
                    raise
                else:
                    self.matNet_orig = hou.selectedNodes()[0]
            except:
                matnets_avail = []
                for child_node in current_tab_parent.children():
                    if child_node.type().name() == "matnet":
                        matnets_avail.append(child_node)
                        self.matNet_orig = matnets_avail[0]
            #         print(f"current for loop node is: {child_node} of type {child_node.type()}")
            #     print(f"matnets_avail = {matnets_avail}")
            # print(f"current node children list: {current_tab_parent.children()}")
        else:
            self.matNet_orig = current_tab_parent

        if self.matNet_orig.type().name() != "matnet":
            print(f"there was an error, you should be selecting a material Network or be inside of one!")


        self.matNet_orig_name = self.matNet_orig.name()
        self.matNet_to_use = self.matNet_orig  # matnet to use is the orig
        self.shadersList = list(self.matNet_orig.children())  # get all shaders
        print(f"self.matNet_to_use is {self.matNet_to_use}")



    def createMatNet(self):
        # matNet_to_use is now the new one
        self.matNet_to_use = self.matNet_orig.parent().createNode("matnet",
                                                                    "materials")

        self.matNet_to_use.moveToGoodPosition()

    def get_Shaders_type(self):
        # create a list of names and types + we already got self.ShaderList
        self.shader_type_list = []
        self.shader_name_list = []
        for shader in self.shadersList:
            self.shader_type_list.append(shader.type().name())
            self.shader_name_list.append(shader.name())
        print(f"printing self.shader_name_list = {self.shader_name_list}")
        print(f"printing self.shaderList = {self.shadersList}")
        print(f"printing type of self.shaderList = {type(self.shadersList)}")

    def getTextureMapsUsed(self):
        for index, shader in enumerate(self.shadersList):
            if self.shader_type_list[index] == "principledshader::2.0":
                self.baseClr_full_string = shader.evalParm("basecolor_texture")
                self.roughness_full_string = shader.evalParm("rough_texture")
                self.metallic_full_string = shader.evalParm("metallic_texture")
                self.normal_full_string = shader.evalParm("baseNormal_texture")

                self.texture_path = os.path.split(self.baseClr_full_string)[0]

                self.baseClr = os.path.split(self.baseClr_full_string)[1]
                self.roughness = os.path.split(self.roughness_full_string)[1]
                self.metallic = os.path.split(self.metallic_full_string)[1]
                self.normal = os.path.split(self.normal_full_string)[1]
                print(f"printing texture_path now set to {self.texture_path}")
                print(
                    f"printing list of shaders: {self.baseClr, self.roughness, self.metallic, self.normal}")

    def createArnoldMaterials(self):
        print(f"printing self.matNet_to_use is of type : {self.matNet_to_use}")

        for index, shader in enumerate(self.shadersList):
            if self.shader_type_list[index] == "principledshader::2.0":
                ArnoldVopNet = self.matNet_to_use.createNode(
                    "arnold_materialbuilder", self.shader_name_list[index])
                ArnoldMatOutput = ArnoldVopNet.children()[0]  # sel Output VOP
                ArnoldMat = ArnoldVopNet.createNode(
                    "arnold::standard_surface")  # create Arnold VOPNet
                ArnoldMatOutput.setInput(0, ArnoldMat)  # connect nodes

                # set parameters
                ArnoldMat.parm("specular").set(0)
                ArnoldMat.parm("specular_roughness").set(1)

                if (self.baseClr != ""):  # create base texture node
                    ArnoldTexBaseColor = ArnoldVopNet.createNode(
                        "arnold::image", "baseColor_map")
                    ArnoldTexBaseColor.parm("filename").set(
                        self.texture_path + self.baseClr)
                    ArnoldMat.setInput(1, ArnoldTexBaseColor)

                if (self.roughness != ""):  # create roughness texture node
                    ArnoldTexRough = ArnoldVopNet.createNode("arnold::image",
                                                             "roughness_map")
                    ArnoldTexRough.parm("filename").set(
                        self.texture_path + self.roughness)
                    ArnoldMat.setInput(6, ArnoldTexRough)

                if (self.metallic != ""):  # create self.metallic texture node
                    ArnoldTexMetal = ArnoldVopNet.createNode("arnold::image",
                                                             "metallic_map")
                    ArnoldTexMetal.parm("filename").set(
                        self.texture_path + self.metallic)
                    ArnoldMat.setInput(3, ArnoldTexMetal)

                if (self.normal != ""):  # create normal texture node
                    ArnoldTexNormal = ArnoldVopNet.createNode("arnold::image",
                                                              "normal_map")
                    ArnoldTexNormal.parm("filename").set(
                        self.texture_path + self.normal)
                    ArnoldNormalMap = ArnoldVopNet.createNode(
                        "arnold::normal_map")
                    ArnoldNormalMap.parm("color_to_signed").set(0)
                    ArnoldNormalMap.setInput(0, ArnoldTexNormal)
                    ArnoldMat.setInput(39, ArnoldNormalMap)

                self.matNet_to_use.layoutChildren()
                ArnoldVopNet.layoutChildren()







''' TO DO LIST:
1. select type of conversion from principled to [RS, Arnold, RM] [BIG TO DO]
    if shader is principled  # simple check #:
        for each selected shader:
            arnoldShaderConverter()

2.maybe not create a new MatNet: [DONE]
    if not (self.matNet_to_use):
        ArnoldVopNet = self.matNet_to_use.createNode("arnold_materialbuilder",shader.name())
    else:
        ArnoldVopNet = self.MatNet_orig.createNode("arnold_materialbuilder",shader.name())

3. get_texture_maps should be its specific function [DONE]
4. creating texture maps nodes for Arnold should be in their own module
5. for shader in self.shadersList: [40% done]
        get the current shader type
        getTextureMapsUsed() to extract the available texture maps
        either create a new Mat Network or not
        run createArnoldMaterials()
        
6. clean MatNet_to_use()

'''




# p1 = r"$HIP/folder1/folder2/baseColor.jpeg"
# p2 = r"$HIP\folder1\folder2\baseColor.jpeg"
#
# print(os.path.split(p1)[-1])
# print(os.path.split(p2)[-1])
