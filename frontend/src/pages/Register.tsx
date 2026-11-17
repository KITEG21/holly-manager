import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { homeFor, useAuth } from "../auth";
import { Button, ErrorText, Input } from "../components/ui";
import { AuthLayout } from "./Login";

export default function Register() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await register(name, email, password);
      navigate("/chat", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout title="Tell us about your project" subtitle="Create your account and in a few minutes your idea will be turned into a plan.">
      <form className="space-y-4" onSubmit={submit}>
        <Input label="Name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Input label="Email" type="email" autoComplete="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <Input
          label="Password (at least 8 characters)"
          type="password"
          autoComplete="new-password"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" className="w-full" loading={pending}>
          Create account
        </Button>
        <ErrorText error={error} />
      </form>
      <p className="mt-8 text-center text-sm text-zinc-500">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
