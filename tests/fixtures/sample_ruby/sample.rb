# Top level comment
# with multiple lines
# @param x [Integer]
def top_level_method(x)
end

# Module comment
module MyModule
  # Constant comment
  MY_CONST = "hello"

  def module_method
  end
end

# Class comment
class MyClass < MyBase
  include MyMixin
  extend MyExtend
  prepend MyPrepend

  # Name property
  attr_accessor :name
  # Age property
  attr_reader "age"
  # Secret property
  attr_writer :secret

  def initialize(name)
    @name = name
  end

  def public_method
  end

  protected

  def protected_method
  end

  private

  def private_method
  end
end
