
def named_references_with_class(mi_context, mi_props, cls):
    from misuka import Properties
    result = []
    for key in mi_props.keys():
        if mi_props.type(key) != Properties.Type.ResolvedReference:
            continue
        ref_index = mi_props.get(key).index()
        props = mi_context.mi_scene_props.get_with_index_and_class(ref_index, cls)
        if props is not None:
            result.append(props)
    return result
