/** Logo da Serrano: montanhas + nome. Herda a cor do texto (currentColor). */
export function Marca({ className = "", tamanho = 24, nome = true }: { className?: string; tamanho?: number; nome?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`} aria-label="Serrano">
      <svg viewBox="0 0 64 44" width={tamanho * 1.45} height={tamanho} aria-hidden="true">
        <path d="M3 41 17 15l10 17L39 7l22 34" fill="none" stroke="currentColor" strokeWidth={8} strokeMiterlimit={10} />
      </svg>
      {nome && (
        <span className="font-marca font-extrabold tracking-[-0.02em]" style={{ fontSize: tamanho * 1.05, lineHeight: 1 }}>
          Serrano
        </span>
      )}
    </span>
  );
}
