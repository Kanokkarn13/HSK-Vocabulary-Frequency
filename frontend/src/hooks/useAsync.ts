import axios from "axios";
import { useEffect, useRef, useState } from "react";

type AsyncState<T> =
  | { status: "loading"; data?: undefined; error?: undefined }
  | { status: "error"; data?: undefined; error: string }
  | { status: "success"; data: T; error?: undefined };

export const GENERIC_ERROR_MESSAGE = "ไม่สามารถโหลดข้อมูลได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง";

export function toErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    if (err.code === "ERR_NETWORK") return GENERIC_ERROR_MESSAGE;
    if (typeof err.response?.data?.detail === "string") return err.response.data.detail;
  }
  return GENERIC_ERROR_MESSAGE;
}

export function useAsync<T>(
  fn: () => Promise<T>,
  deps: React.DependencyList,
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const requestId = useRef(0);

  useEffect(() => {
    const id = ++requestId.current;
    setState({ status: "loading" });
    fn()
      .then((data) => {
        if (requestId.current === id) setState({ status: "success", data });
      })
      .catch((err: unknown) => {
        if (requestId.current !== id) return;
        console.error(err);
        setState({ status: "error", error: toErrorMessage(err) });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
