import { useState, useEffect } from "react";
import { CareCase } from "../types";
import { fetchCases } from "../services/api";

export function useCases() {
  const [cases, setCases] = useState<CareCase[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const res = await fetchCases();
        if (Array.isArray(res)) {
          setCases(res);
        } else if ((res as any)?.data && Array.isArray((res as any).data)) {
          setCases((res as any).data);
        }
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return { cases, loading, error };
}
