import { useEffect, useState } from "react";
import { fetchSchema } from "../api/client";
import type { SchemaPayload } from "../api/types";

export function useSchema() {
  const [schema, setSchema] = useState<SchemaPayload | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    fetchSchema()
      .then((s) => vivo && setSchema(s))
      .catch((e: unknown) => vivo && setErro(e instanceof Error ? e.message : String(e)));
    return () => {
      vivo = false;
    };
  }, []);

  return { schema, erro };
}
