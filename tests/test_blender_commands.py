from materials_processor.dcc.blender import commands


def test_ingest_material_uses_fresh_reader(monkeypatch):
    material = object()
    expected = object()
    seen = []

    class FakeReader:
        def analyze(self, received_material):
            seen.append(received_material)
            return expected

    monkeypatch.setattr(commands, "BlenderMaterialReader", FakeReader)

    assert commands.ingest_material(material) is expected
    assert seen == [material]


def test_run_delegates_to_single_material_adapter(monkeypatch):
    material = object()
    expected = object()
    seen = []
    monkeypatch.setattr(
        commands,
        "convert_material",
        lambda received_material, *, target_name: seen.append((received_material, target_name)) or expected,
    )

    assert commands.run(material, target_name="rebuilt") is expected
    assert seen == [(material, "rebuilt")]


def test_run_for_active_object_delegates_to_active_material_adapter(monkeypatch):
    active_object = object()
    expected = object()
    seen = []
    monkeypatch.setattr(
        commands,
        "convert_active_material",
        lambda received_object, *, target_name: seen.append((received_object, target_name)) or expected,
    )

    assert commands.run_for_active_object(active_object, target_name="rebuilt") is expected
    assert seen == [(active_object, "rebuilt")]


def test_run_for_selected_objects_delegates_a_list_to_batch_adapter(monkeypatch):
    objects = (object(), object())
    expected = (object(),)
    seen = []
    monkeypatch.setattr(
        commands,
        "convert_selected_active_materials",
        lambda received_objects: seen.append(received_objects) or expected,
    )

    assert commands.run_for_selected_objects(objects) is expected
    assert seen == [list(objects)]
