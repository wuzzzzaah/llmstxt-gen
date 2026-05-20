defmodule SampleModule.Core do
  @moduledoc """
  A sample Elixir module for testing.
  """

  @behaviour SampleBehaviour

  @constant_attr "value"

  defstruct [:name, :age]

  @doc "Greets the user."
  @spec hello(String.t()) :: :ok
  def hello(name) do
    IO.puts("Hello, #{name}")
  end

  @doc "A function with multiple heads."
  def multi(1), do: 1
  def multi(n), do: n

  defp secret_func do
    :secret
  end

  @doc "A macro."
  defmacro my_macro(expr) do
    expr
  end
end

defprotocol SampleProtocol do
  @doc "Protocol function."
  def foo(x)
end

defimpl SampleProtocol, for: Integer do
  def foo(i), do: i
end
