from materials_processor.core.conversion import ConversionService
from materials_processor.core.graph import MaterialGraph


class FakeReader:
    def __init__(self):
        self.seen_material = None

    def read(self, native_material):
        self.seen_material = native_material
        return MaterialGraph(material_name="source_graph")


class FakeWriter:
    def __init__(self):
        self.seen_graph = None
        self.seen_context = None

    def write(self, graph, target_context):
        self.seen_graph = graph
        self.seen_context = target_context
        return {"created": graph.material_name, "context": target_context}


def test_conversion_service_passes_graph_from_reader_to_writer():
    reader = FakeReader()
    writer = FakeWriter()

    result = ConversionService(reader, writer).convert("native_material", "target_context")

    assert reader.seen_material == "native_material"
    assert writer.seen_graph.material_name == "source_graph"
    assert writer.seen_context == "target_context"
    assert result == {"created": "source_graph", "context": "target_context"}
