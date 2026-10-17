import { Suspense } from "react";
import { backendFetch } from "@/lib/backend";
import styles from "./page.module.css";

async function getBackendStatus(): Promise<string | null> {
  try {
    const { status } = await backendFetch<{ status: string }>("/health");
    return status;
  } catch {
    return null;
  }
}

async function BackendStatus() {
  const status = await getBackendStatus();
  if (status === null) {
    return (
      <p className={styles.ng}>
        バックエンドに接続できません (backend で uvicorn を起動してください)
      </p>
    );
  }
  return <p className={styles.ok}>バックエンド: {status}</p>;
}

export default function Home() {
  return (
    <main className={styles.main}>
      <h1>develop_assistant</h1>
      <Suspense fallback={<p>バックエンドを確認中...</p>}>
        <BackendStatus />
      </Suspense>
    </main>
  );
}
