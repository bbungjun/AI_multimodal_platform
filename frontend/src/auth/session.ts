// Collection-safe interface skeleton. Todo 2 replaces the RED behavior.
export function safeReturnPath(_value: string): string { return "/generate"; }
export function createSession(_deps: { me(): Promise<unknown>; now(): number }) {
  return {
    getSnapshot: () => ({ kind: "checking" }),
    retry: async () => {},
    logout: async () => {},
    activity: async (_visible: boolean) => {},
  };
}
