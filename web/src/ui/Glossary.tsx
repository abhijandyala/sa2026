import type { ReactNode } from "react";
import { GLOSSARY, type TermId } from "../content/glossary";
import { Term } from "./components";

/** An inline term the reader can tap for a plain definition (card 6.6). */
export function G({ id, children }: { id: TermId; children?: ReactNode }) {
  const g = GLOSSARY[id];
  return (
    <Term term={typeof children === "string" ? children : g.term.toLowerCase()}>
      <strong>{g.term}.</strong> {g.definition}
    </Term>
  );
}
