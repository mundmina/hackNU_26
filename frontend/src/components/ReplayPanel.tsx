import type { EnrichedTelemetry } from "../types";

interface ReplayPanelProps {
  history: EnrichedTelemetry[];
  replayIndex: number;
  onReplayIndexChange: (value: number) => void;
  onPlay: () => void;
  playing: boolean;
}

export function ReplayPanel({ history, replayIndex, onReplayIndexChange, onPlay, playing }: ReplayPanelProps) {
  const current = history[replayIndex] ?? history[0];

  return (
    <section className="panel replay-panel">
      <div className="panel-header">
        <p>История и воспроизведение</p>
        <button className="ghost-button" onClick={onPlay}>
          {playing ? "Пауза" : "Воспроизвести"}
        </button>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(history.length - 1, 0)}
        value={replayIndex}
        onChange={(event) => onReplayIndexChange(Number(event.target.value))}
      />
      <div className="replay-meta">
        <span>{current ? new Date(current.telemetry.timestamp).toLocaleString("ru-RU") : "История пока отсутствует"}</span>
        <span>{current ? `${current.health.score.toFixed(1)} / ${current.health.grade}` : "Ожидание данных для воспроизведения"}</span>
      </div>
    </section>
  );
}
