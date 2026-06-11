import { LAYER_REGISTRY } from "../layers";

interface LayerToggleProps {
  visibility: Record<string, boolean>;
  onToggle: (layerId: string) => void;
}

export function LayerToggle({ visibility, onToggle }: LayerToggleProps) {
  return (
    <section className="panel layer-toggle" aria-label="Layers">
      <h2 className="panel-title">Layers</h2>
      <ul className="layer-list">
        {LAYER_REGISTRY.map((layer) => {
          const visible = visibility[layer.id] ?? layer.defaultVisible;
          return (
            <li key={layer.id}>
              <label className="layer-item">
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={() => onToggle(layer.id)}
                />
                <span>{layer.label}</span>
              </label>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
