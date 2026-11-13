/*
  Rolling number (theme kit). Digits roll to their new value when the number changes, the
  way a counter does; everything else stays put. Screen readers get the plain value.
  Digits are keyed from the right, so "437" to "46" rolls the tens and ones in place.
*/
const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];

export function Roll({ value, className }: { value: string; className?: string }) {
  const chars = [...value];
  return (
    <span className={`roll${className ? ` ${className}` : ""}`}>
      <span className="visually-hidden">{value}</span>
      <span className="roll-row" aria-hidden="true">
        {chars.map((ch, i) => {
          const fromRight = chars.length - i;
          return /\d/.test(ch) ? (
            <span key={`d${fromRight}`} className="roll-col">
              <span className="roll-stack" style={{ transform: `translateY(${-Number(ch) * 10}%)` }}>
                {DIGITS.map((d) => (
                  <span key={d}>{d}</span>
                ))}
              </span>
            </span>
          ) : (
            <span key={`c${fromRight}`} className="roll-char">
              {ch}
            </span>
          );
        })}
      </span>
    </span>
  );
}
