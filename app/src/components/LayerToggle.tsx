import { LAYER_REGISTRY } from "../layers";

interface LayerToggleProps {
  visibility: Record<string, boolean>;
  onToggle: (layerId: string) => void;
  /**
   * Whether each toggle's underlying data is present. Layers marked
   * `requiresData` are hidden entirely until their entry here is true.
   */
  availability?: Record<string, boolean>;
}

export function LayerToggle({ visibility, onToggle, availability }: LayerToggleProps) {
  const layers = LAYER_REGISTRY.filter(
    (layer) => !layer.requiresData || (availability?.[layer.id] ?? false),
  );
  if (layers.length === 0) return null;
  return (
    <section className="panel layer-toggle" aria-label="Layers">
      <h2 className="panel-title">Layers</h2>
      <ul className="layer-list">
        {layers.map((layer) => {
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
