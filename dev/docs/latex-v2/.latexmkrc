# Teaches latexmk how to build the nomenclature list (nomencl package).
# Without this, latexmk doesn't know .nlo -> .nls needs a makeindex pass with
# the nomencl.ist style, so \printnomenclature in main.tex silently stays
# empty ("No file main.nls." in the .log) even though main.nlo fills up fine.
add_cus_dep('nlo', 'nls', 0, 'makeindex2nomencl');
sub makeindex2nomencl {
    system("makeindex -s nomencl.ist -o \"$_[0].nls\" \"$_[0].nlo\"");
}
